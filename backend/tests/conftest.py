"""Shared test-only configuration; production authentication remains fail-closed.

CI tidak punya berkas ``backend/.env`` (memang gitignored), jadi suite ini TIDAK BOLEH
bergantung pada kredensial developer. Nilai di bawah adalah placeholder palsu untuk kode
yang hanya butuh "env terisi", bukan untuk benar-benar memanggil provider.
"""
import os

import pytest

# Existing integration tests exercise endpoint workflows without credentials. Make this
# deliberate, test-only development opt-in explicit rather than weakening app defaults.
os.environ.setdefault("ALLOW_UNAUTHENTICATED_DEV", "true")
# Hermetik: kunci API dari .env lokal developer tidak boleh membuat test endpoint jadi 401.
os.environ["GTNIC_API_KEY"] = ""

# Placeholder kredensial: cukup agar gerbang kredensial lolos, tidak dipakai untuk request nyata.
os.environ.setdefault("GROQ_API_KEYS", "test-groq-key-1")
os.environ.setdefault("IG_TOKEN", "test-instagram-token")
os.environ.setdefault("IG_USER_ID", "17841400000000000")
os.environ.setdefault("CLOUDINARY_CLOUD_NAME", "test-cloud")
os.environ.setdefault("CLOUDINARY_API_KEY", "test-key")
os.environ.setdefault("CLOUDINARY_API_SECRET", "test-secret")


@pytest.fixture(autouse=True)
def _offline_provider_quota(monkeypatch):
    """Blokir satu-satunya panggilan jaringan implisit di alur publikasi.

    ``publisher.check_publishing_quota`` memanggil Graph API dan menelan exception,
    sehingga tanpa stub ini setiap test publikasi diam-diam melakukan request nyata
    (lambat & flaky di CI). Kuota default dibuat longgar supaya test tidak terblokir.
    """
    from src.tools import instagram

    monkeypatch.setattr(
        instagram,
        "get_content_publishing_limit",
        lambda ctx=None: {"quota_usage": 0, "config": {"quota_total": 100, "quota_duration": 86400}},
    )
