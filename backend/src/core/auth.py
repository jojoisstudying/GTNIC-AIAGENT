"""API Security & Authentication dependency for GTNIC Enterprise Agent.

Provides API-key authentication for protected endpoints. Production always requires
Production always requires GTNIC_API_KEY; unauthenticated development mode must
be explicitly opted into with ALLOW_UNAUTHENTICATED_DEV=true.
"""
import os
import hmac
from typing import Optional
from fastapi import HTTPException, Security, status
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
        environment = os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "development")).strip().lower()
        if environment in {"production", "prod"}:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                 detail="Autentikasi API belum dikonfigurasi untuk production.")
        if os.getenv("ALLOW_UNAUTHENTICATED_DEV", "").lower() != "true":
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                 detail="Set GTNIC_API_KEY atau aktifkan mode development terbuka secara eksplisit.")
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
