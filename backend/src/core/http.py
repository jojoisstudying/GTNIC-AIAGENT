"""HTTP requests with timeouts, bounded retries, secret redaction, and error detail extraction.

Provider error bodies are surfaced (sanitized) instead of being replaced with a generic
"HTTP request failed" wrapper: that old behaviour hid truly actionable causes such as
Cloudinary's "Stale request" (clock skew) or Meta's permission/param errors.
"""
from email.utils import parsedate_to_datetime
import json
import re
import time
from typing import Any
from urllib.parse import parse_qsl, urlsplit, urlunsplit

import requests
from requests import Response

from src.core.events import EventEmitter


_SECRET_KEYS = {"access_token", "api_key", "apikey", "token", "authorization", "x-api-key",
                "api_secret", "signature", "sig"}
_SECRET_PATTERN = re.compile(r"(?i)(access_token|api_key|api_secret|authorization|signature)(\s*[=:]\s*)([^\s&,;]+)")
_SECRET_QUERY_PATTERN = re.compile(r"(?i)(access_token|api_key|apikey|token|signature)(=|%3D)([^\s&,;]+)")
_RETRYABLE_STATUS = {408, 425, 429}
MAX_DETAIL_CHARS = 400


class HttpError(RuntimeError):
    """Provider HTTP failure carrying status code and a sanitized provider message.

    Only non-secret context is exposed so callers can log/persist it safely.
    """

    def __init__(self, message: str, *, provider: str = "", status_code: int | None = None,
                 provider_message: str = "", retryable: bool = False) -> None:
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code
        self.provider_message = provider_message
        self.retryable = retryable


def redact_url(url: str) -> str:
    """Remove secret query parameters from a URL while retaining non-secret context."""
    parts = urlsplit(url)
    query = [(key, "[REDACTED]" if key.lower() in _SECRET_KEYS else value)
             for key, value in parse_qsl(parts.query, keep_blank_values=True)]
    safe_query = "&".join(f"{key}={value}" for key, value in query)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, safe_query, ""))


def redact_text(text: str) -> str:
    """Redact common credential assignments from arbitrary response/error text."""
    sanitized = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1[REDACTED]", text)
    sanitized = _SECRET_PATTERN.sub(r"\1\2[REDACTED]", sanitized)
    sanitized = _SECRET_QUERY_PATTERN.sub(r"\1\2[REDACTED]", sanitized)
    return sanitized


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return ""


def extract_error_message(response: Response) -> str:
    """Pull the human-readable provider error out of a response body.

    Understands Cloudinary (``{"error": {"message": ...}}``), Meta Graph
    (``{"error": {"message","code","error_subcode","type"}}``), FastAPI ``detail``,
    and plain-text bodies. Never raises; returns "" when nothing readable is found.
    """
    try:
        raw = response.content or b""
    except Exception:  # pragma: no cover - defensive: stream already consumed
        return ""
    text = _decode(raw).strip()
    if not text:
        return ""
    try:
        data = json.loads(text)
    except ValueError:
        data = None

    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict):
            parts = [str(err.get("message") or err.get("detail") or "").strip()]
            if err.get("code") not in (None, ""):
                parts.append(f"code={err.get('code')}")
            if err.get("error_subcode"):
                parts.append(f"subcode={err.get('error_subcode')}")
            if err.get("type"):
                parts.append(str(err.get("type")))
            joined = " | ".join(p for p in parts if p)
            if joined:
                return joined[:MAX_DETAIL_CHARS]
        elif isinstance(err, str) and err.strip():
            return err.strip()[:MAX_DETAIL_CHARS]
        detail = data.get("detail")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()[:MAX_DETAIL_CHARS]
        if isinstance(detail, list) and detail:
            first = detail[0]
            if isinstance(first, dict) and first.get("msg"):
                return str(first["msg"])[:MAX_DETAIL_CHARS]
    return text[:MAX_DETAIL_CHARS]


class HttpClient:
    """Requests-compatible HTTP helper with a bounded retry policy."""

    def __init__(self, emitter: EventEmitter | None = None, *, timeout: float = 30.0,
                 max_attempts: int = 4, session: requests.Session | None = None) -> None:
        if timeout <= 0 or max_attempts < 1:
            raise ValueError("timeout and max_attempts must be positive")
        self.emitter = emitter
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.session = session or requests.Session()

    def request(self, method: str, url: str, *, step: str, provider: str,
                timeout: float | None = None, units: float | None = None,
                **kwargs: Any) -> Response:
        """Perform a request, retrying transient failures and emitting sanitized telemetry."""
        effective_timeout = timeout if timeout is not None else self.timeout
        if effective_timeout <= 0:
            raise ValueError("HTTP timeout must be positive")
        safe_url = redact_url(url)
        started = time.monotonic()
        response: Response | None = None
        try:
            for attempt in range(1, self.max_attempts + 1):
                try:
                    response = self.session.request(method, url, timeout=effective_timeout, **kwargs)
                except (requests.Timeout, requests.ConnectionError) as exc:
                    if attempt >= self.max_attempts:
                        raise HttpError(
                            f"{provider} tidak merespons setelah {attempt} percobaan "
                            f"({type(exc).__name__}); periksa koneksi server.",
                            provider=provider, retryable=True) from None
                    self._retry(step, provider, attempt, "timeout", 2 ** (attempt - 1))
                    time.sleep(2 ** (attempt - 1))
                    continue

                retryable = response.status_code in _RETRYABLE_STATUS or response.status_code >= 500
                if retryable and attempt < self.max_attempts:
                    delay = self._retry_delay(response, attempt)
                    self._retry(step, provider, attempt, f"HTTP {response.status_code}", delay)
                    time.sleep(delay)
                    continue

                if response.status_code >= 400:
                    detail = redact_text(extract_error_message(response))
                    message = f"{provider} HTTP {response.status_code}"
                    if detail:
                        message = f"{message}: {detail}"
                    raise HttpError(message, provider=provider, status_code=response.status_code,
                                    provider_message=detail, retryable=retryable)

                self._emit(step, provider, safe_url, response.status_code, started, "ok", units=units)
                return response
            raise HttpError(f"{provider} request failed after {self.max_attempts} attempts",
                            provider=provider)
        except HttpError as exc:
            self._emit(step, provider, safe_url,
                       exc.status_code or (response.status_code if response is not None else None),
                       started, "error", {"error": redact_text(str(exc))[:500]}, units=units)
            raise
        except Exception as exc:  # noqa: BLE001 - the network stack raises many types
            status_code = response.status_code if response is not None else None
            self._emit(step, provider, safe_url, status_code, started, "error",
                       {"error": redact_text(str(exc))[:500]}, units=units)
            raise HttpError(f"{provider} HTTP request failed ({type(exc).__name__}): "
                            f"{redact_text(str(exc))[:200]}",
                            provider=provider, status_code=status_code) from None

    def _retry_delay(self, response: Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(0.0, min(float(retry_after), 60.0))
            except ValueError:
                try:
                    return max(0.0, min((parsedate_to_datetime(retry_after).timestamp() - time.time()), 60.0))
                except (TypeError, ValueError, OverflowError):
                    pass
        return float(min(2 ** (attempt - 1), 30))

    def _retry(self, step: str, provider: str, attempt: int, reason: str, delay: float) -> None:
        if self.emitter:
            self.emitter.emit("retry", provider, step=step, status="retry",
                              detail={"attempt": attempt, "reason": reason, "delay_seconds": delay})

    def _emit(self, step: str, provider: str, target: str, status_code: int | None,
              started: float, status: str, detail: dict[str, Any] | None = None,
              *, units: float | None = None) -> None:
        if self.emitter:
            event_detail = {"status_code": status_code, **(detail or {})}
            self.emitter.emit("http", provider, step=step, target=target, status=status, units=units,
                              duration_ms=(time.monotonic() - started) * 1000, detail=event_detail)
