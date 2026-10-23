"""Tests for core/credentials.py: expires_at, auto refresh, error 190, alerting."""
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.credentials import (
    CredentialExpiredError,
    CredentialStatus,
    ensure_instagram_credentials,
    refresh_instagram_token,
    send_alert,
)
from src.core.db import Base


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sm = sessionmaker(bind=engine)
    return sm


def test_ensure_instagram_credentials_creates_row_and_returns(monkeypatch, test_db):
    session = test_db()
    monkeypatch.setattr("src.config.opt", lambda k, default="": "fake-token" if k == "IG_TOKEN" else default)

    cred = ensure_instagram_credentials(session)
    assert cred.provider == "instagram"
    assert cred.last_refreshed_at is not None


def test_ensure_instagram_credentials_raises_when_expired(monkeypatch, test_db):
    session = test_db()
    monkeypatch.setattr("src.config.opt", lambda k, default="": "fake-token" if k == "IG_TOKEN" else default)

    alerts = []
    monkeypatch.setattr("src.core.credentials.send_alert", lambda msg, subject="": alerts.append(msg))

    now = datetime.now(timezone.utc)
    expired_time = now - timedelta(days=2)
    cred = CredentialStatus(
        provider="instagram",
        expires_at=expired_time,
        last_refreshed_at=now - timedelta(days=60),
        created_at=now - timedelta(days=60)
    )
    session.add(cred)
    session.commit()

    with pytest.raises(CredentialExpiredError):
        ensure_instagram_credentials(session)

    # Should have sent alert and marked alerted_at
    assert len(alerts) == 1
    session.refresh(cred)
    assert cred.alerted_at is not None

    # Second call should not spam alert (cooldown)
    with pytest.raises(CredentialExpiredError):
        ensure_instagram_credentials(session)
    assert len(alerts) == 1


def test_ensure_instagram_credentials_auto_refresh(monkeypatch, test_db):
    session = test_db()
    monkeypatch.setattr("src.config.opt", lambda k, default="": "valid-token" if k == "IG_TOKEN" else default)

    now = datetime.now(timezone.utc)
    # Token expiring in 2 days (within 7 day default threshold)
    cred = CredentialStatus(
        provider="instagram",
        expires_at=now + timedelta(days=2),
        last_refreshed_at=now - timedelta(days=58),
        created_at=now - timedelta(days=58)
    )
    session.add(cred)
    session.commit()

    refreshed = False
    def mock_refresh(token, http=None):
        nonlocal refreshed
        refreshed = True
        return {"access_token": "new-token", "expires_in": 5184000}

    monkeypatch.setattr("src.core.credentials.refresh_instagram_token", mock_refresh)

    res = ensure_instagram_credentials(session)
    assert refreshed is True
    session.refresh(cred)
    # expires_at should be updated to ~60 days in the future
    exp = cred.expires_at if cred.expires_at.tzinfo is not None else cred.expires_at.replace(tzinfo=timezone.utc)
    assert exp > now + timedelta(days=50)


def test_ensure_instagram_credentials_error_190_alerts_and_fails(monkeypatch, test_db):
    session = test_db()
    monkeypatch.setattr("src.config.opt", lambda k, default="": "bad-token" if k == "IG_TOKEN" else default)

    alerts = []
    monkeypatch.setattr("src.core.credentials.send_alert", lambda msg, subject="": alerts.append(msg))

    now = datetime.now(timezone.utc)
    cred = CredentialStatus(
        provider="instagram",
        expires_at=now + timedelta(days=2),
        created_at=now
    )
    session.add(cred)
    session.commit()

    def mock_refresh_fail(token, http=None):
        raise RuntimeError("Instagram refresh error 190: Error validating access token")

    monkeypatch.setattr("src.core.credentials.refresh_instagram_token", mock_refresh_fail)

    with pytest.raises(CredentialExpiredError):
        ensure_instagram_credentials(session)

    assert len(alerts) == 1
    session.refresh(cred)
    assert cred.alerted_at is not None
    assert "190" in cred.last_error
