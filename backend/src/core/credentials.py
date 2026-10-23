"""Instagram credential verification, auto-refresh, and alerting."""
from datetime import datetime, timedelta, timezone
import json
import os
from typing import Any
import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from src import config
from src.core.db import CredentialStatus, SessionLocal, sessionmaker
from src.core.events import EventEmitter
from src.core.http import HttpClient, redact_text

PROVIDER_NAME = "instagram"


class CredentialExpiredError(RuntimeError):
    """Raised when the Instagram access token is expired and cannot be refreshed."""


def send_alert(message: str, *, subject: str = "Social Media Pipeline Alert") -> bool:
    """Send an alert via Telegram Bot or Email webhook based on environment settings.

    Supported env variables:
      TELEGRAM_BOT_TOKEN & TELEGRAM_CHAT_ID: for Telegram notifications
      ALERT_WEBHOOK_URL: for general HTTP webhook notifications (Slack/Discord/Custom)
    """
    bot_token = config.opt("TELEGRAM_BOT_TOKEN")
    chat_id = config.opt("TELEGRAM_CHAT_ID")
    if bot_token and chat_id:
        try:
            tg_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            requests.post(tg_url, json={"chat_id": chat_id, "text": f"[{subject}]\n{message}"}, timeout=10)
            return True
        except Exception:
            pass

    webhook = config.opt("ALERT_WEBHOOK_URL")
    if webhook:
        try:
            requests.post(webhook, json={"subject": subject, "message": message}, timeout=10)
            return True
        except Exception:
            pass

    # Fallback to stdout alert if no third-party alert channel configured
    print(f"\n[ALERT] {subject}: {message}\n")
    return True


def refresh_instagram_token(current_token: str, *, http: HttpClient | None = None) -> dict[str, Any]:
    """Refresh a long-lived Instagram User Access Token via Graph API.

    Endpoint: GET https://graph.instagram.com/refresh_access_token
    Params: grant_type=ig_refresh_token, access_token=...
    Returns dict containing 'access_token' and 'expires_in' (seconds).
    """
    base_url = config.opt("IG_API_BASE", "https://graph.instagram.com")
    url = f"{base_url}/refresh_access_token"
    params = {"grant_type": "ig_refresh_token", "access_token": current_token}

    if http:
        resp = http.request("GET", url, step="credentials", provider="instagram", params=params, timeout=30)
        data = resp.json()
    else:
        resp = requests.get(url, params=params, timeout=30)
        data = resp.json()

    if "error" in data:
        err = data["error"]
        msg = err.get("message", "unknown error")
        code = err.get("code")
        raise RuntimeError(f"Instagram refresh error {code}: {msg}")

    return data


def ensure_instagram_credentials(session: Session, *, http: HttpClient | None = None,
                                  emitter: EventEmitter | None = None,
                                  refresh_threshold_days: int = 7,
                                  alert_cooldown_hours: int = 12) -> CredentialStatus:
    """Check Instagram token validity, refresh if close to expiry, or send alert if expired/error 190.

    Raises CredentialExpiredError if the token is already expired or refresh fails.
    """
    now = datetime.now(timezone.utc)
    status_row = session.get(CredentialStatus, PROVIDER_NAME)
    if not status_row:
        status_row = CredentialStatus(
            provider=PROVIDER_NAME,
            last_refreshed_at=now,
            created_at=now
        )
        session.add(status_row)
        session.commit()

    token = config.opt("IG_TOKEN")
    if not token:
        msg = "Token Instagram (IG_TOKEN) tidak ditemukan di konfigurasi env"
        status_row.last_error = msg
        session.commit()
        raise CredentialExpiredError(msg)

    def _to_utc(dt: datetime | None) -> datetime | None:
        if dt is None:
            return None
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)

    expires_at = _to_utc(status_row.expires_at)
    alerted_at = _to_utc(status_row.alerted_at)

    # Check if currently expired
    if expires_at and expires_at <= now:
        _handle_alert_and_error(session, status_row, f"Token Instagram kedaluwarsa pada {expires_at}",
                                alert_cooldown_hours, emitter)
        raise CredentialExpiredError(f"Token Instagram kedaluwarsa pada {expires_at}. Harap update .env")

    # If expires_at is set and within threshold, attempt automatic refresh
    needs_refresh = False
    if expires_at:
        remaining = expires_at - now
        if remaining <= timedelta(days=refresh_threshold_days):
            needs_refresh = True

    if needs_refresh:
        try:
            res = refresh_instagram_token(token, http=http)
            new_token = res.get("access_token")
            expires_in = res.get("expires_in", 5184000) # default ~60 days
            status_row.expires_at = now + timedelta(seconds=expires_in)
            status_row.last_refreshed_at = now
            status_row.last_error = None
            session.commit()
            if emitter:
                emitter.emit("info", "ig_token_refreshed", step="credentials", status="ok",
                             detail={"expires_at": status_row.expires_at.isoformat()})
        except Exception as exc:
            err_msg = redact_text(str(exc))
            status_row.last_error = err_msg
            session.commit()
            _handle_alert_and_error(session, status_row, f"Gagal me-refresh token IG: {err_msg}",
                                    alert_cooldown_hours, emitter)
            if "190" in err_msg or (expires_at and expires_at <= now):
                raise CredentialExpiredError(f"Token IG tidak dapat di-refresh: {err_msg}") from None

    return status_row


def _handle_alert_and_error(session: Session, status_row: CredentialStatus, message: str,
                            cooldown_hours: int, emitter: EventEmitter | None) -> None:
    now = datetime.now(timezone.utc)
    should_alert = True
    alerted_at = status_row.alerted_at
    if alerted_at is not None and alerted_at.tzinfo is None:
        alerted_at = alerted_at.replace(tzinfo=timezone.utc)
    if alerted_at:
        elapsed = now - alerted_at
        if elapsed < timedelta(hours=cooldown_hours):
            should_alert = False

    if should_alert:
        send_alert(message, subject="Instagram Token Error")
        status_row.alerted_at = now
        session.commit()
        if emitter:
            emitter.emit("info", "token_alert_sent", step="credentials", status="alerted",
                         detail={"message": message})
