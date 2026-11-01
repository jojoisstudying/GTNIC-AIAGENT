"""API Security & Authentication dependency for GTNIC Enterprise Agent.

Provides optional/required API key authentication for mutating and admin endpoints.
Can be configured via GTNIC_API_KEY environment variable. If empty or not set,
in development mode it logs a warning and permits requests, but enforces protection
when GTNIC_API_KEY is configured.
"""
import os
import hmac
from typing import Optional
from fastapi import Header, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from src import config

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_configured_api_key() -> str:
    return config.opt("GTNIC_API_KEY", "").strip()


async def verify_api_key(api_key: Optional[str] = Security(API_KEY_HEADER)) -> bool:
    """Verifies the X-API-Key header.
    If GTNIC_API_KEY is defined in environment, any request without a valid matching key is rejected.
    """
    configured = get_configured_api_key()
    if not configured:
        # Development mode default: open if not explicitly configured
        return True

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Header 'X-API-Key' diperlukan untuk endpoint terproteksi.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if not hmac.compare_digest(api_key.strip(), configured):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API Key tidak valid atau tidak memiliki otorisasi.",
        )

    return True
