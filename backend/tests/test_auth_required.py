"""Regression tests for fail-closed API key configuration."""
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.core import auth


@pytest.mark.asyncio
async def test_auth_rejects_missing_key_when_not_explicitly_open(monkeypatch):
    monkeypatch.setattr(auth, "get_configured_api_key", lambda: "")
    monkeypatch.delenv("ALLOW_UNAUTHENTICATED_DEV", raising=False)
    monkeypatch.setenv("APP_ENV", "development")
    with pytest.raises(HTTPException) as exc:
        await auth.verify_api_key(None)
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_auth_allows_missing_key_only_with_explicit_dev_override(monkeypatch):
    monkeypatch.setattr(auth, "get_configured_api_key", lambda: "")
    monkeypatch.setenv("ALLOW_UNAUTHENTICATED_DEV", "true")
    monkeypatch.setenv("APP_ENV", "development")
    assert await auth.verify_api_key(None) is True


@pytest.mark.asyncio
async def test_auth_rejects_unconfigured_production(monkeypatch):
    monkeypatch.setattr(auth, "get_configured_api_key", lambda: "")
    monkeypatch.setenv("ALLOW_UNAUTHENTICATED_DEV", "true")
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(HTTPException) as exc:
        await auth.verify_api_key(None)
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_auth_validates_configured_key(monkeypatch):
    monkeypatch.setattr(auth, "get_configured_api_key", lambda: "secret-test-key")
    with pytest.raises(HTTPException) as missing:
        await auth.verify_api_key(None)
    assert missing.value.status_code == 401
    with pytest.raises(HTTPException) as invalid:
        await auth.verify_api_key("wrong")
    assert invalid.value.status_code == 403
    assert await auth.verify_api_key("secret-test-key") is True


@pytest.mark.asyncio
async def test_auth_accepts_configured_key_with_whitespace_trim(monkeypatch):
    monkeypatch.setattr(auth, "get_configured_api_key", lambda: "secret-test-key")
    assert await auth.verify_api_key("  secret-test-key  ") is True


def test_production_app_startup_fails_without_api_key(monkeypatch):
    from src.api import app

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(auth, "get_configured_api_key", lambda: "")
    with pytest.raises(RuntimeError, match="GTNIC_API_KEY"):
        with TestClient(app):
            pass
