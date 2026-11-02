"""Tests for file validation and path traversal security on asset/logo uploads (BUG-06)."""
import io
import pytest
from fastapi.testclient import TestClient
from fastapi import UploadFile, HTTPException
from PIL import Image

from src.api import app, _validate_image_file


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("src.api.config.ROOT", tmp_path)
    app.state.root = tmp_path
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "brand.json").write_text("{}", encoding="utf-8")
    return TestClient(app)


def _create_test_image(format="PNG", size=(100, 100), color="blue"):
    buf = io.BytesIO()
    im = Image.new("RGB", size, color=color)
    im.save(buf, format=format)
    buf.seek(0)
    return buf.getvalue()


def test_valid_logo_upload(client):
    img_bytes = _create_test_image("JPEG")
    files = {"file": ("logo.jpeg", img_bytes, "image/png")}
    res = client.post("/api/v1/brand/logo", files=files)
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    saved = __import__("pathlib").Path(res.json()["path"])
    assert saved.suffix == ".png"
    with Image.open(saved) as image:
        assert image.format == "PNG"


def test_invalid_image_corrupt_rejected(client):
    files = {"file": ("corrupt.png", b"NOT_A_VALID_IMAGE_HEADER_12345", "image/png")}
    res = client.post("/api/v1/brand/logo", files=files)
    assert res.status_code == 400
    assert "tidak valid" in res.json()["detail"].lower()
    assert not (client.app.state.root / "assets" / "logo.png").exists()


def test_spoofed_content_type_does_not_override_actual_format(client):
    jpeg_bytes = _create_test_image("JPEG")
    response = client.post("/api/v1/brand/logo", files={"file": ("fake.png", jpeg_bytes, "image/png")})
    assert response.status_code == 200
    with Image.open(client.app.state.root / "assets" / "logo.png") as image:
        assert image.format == "PNG"


def test_empty_file_rejected(client):
    files = {"file": ("empty.png", b"", "image/png")}
    res = client.post("/api/v1/brand/logo", files=files)
    assert res.status_code == 400
    assert "kosong" in res.json()["detail"].lower()


def test_extreme_image_dimensions_are_rejected_before_decode(client):
    import struct
    import zlib

    width = height = 7000  # valid PNG header, deliberately exceeds 40 megapixels
    raw = b"\x00" + b"\x00\x00\x00" * width
    compressed = zlib.compress(raw)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II5B", width, height, 8, 2, 0, 0, 0)
        + struct.pack(">I", zlib.crc32(b"IHDR" + struct.pack(">II5B", width, height, 8, 2, 0, 0, 0)) & 0xFFFFFFFF)
        + struct.pack(">I", len(compressed)) + b"IDAT" + compressed
        + struct.pack(">I", zlib.crc32(b"IDAT" + compressed) & 0xFFFFFFFF)
        + struct.pack(">I", 0) + b"IEND" + struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)
    )
    response = client.post("/api/v1/brand/logo", files={"file": ("huge.png", png, "image/png")})
    assert response.status_code == 400
    assert "Resolusi" in response.json()["detail"]


def test_oversized_file_rejected():
    fake_file = UploadFile(filename="huge.png", file=io.BytesIO(b"X" * (6 * 1024 * 1024)))
    with pytest.raises(HTTPException) as exc:
        _validate_image_file(fake_file, max_mb=5.0)
    assert exc.value.status_code == 400
    assert "melebihi batas" in exc.value.detail


def test_oversized_file_stops_reading_at_limit():
    class CountingFile(io.BytesIO):
        bytes_read = 0

        def read(self, size=-1):
            data = super().read(size)
            self.bytes_read += len(data)
            return data

    backing = CountingFile(b"X" * (8 * 1024 * 1024))
    fake_file = UploadFile(filename="huge.png", file=backing)
    with pytest.raises(HTTPException):
        _validate_image_file(fake_file, max_mb=1.0)
    assert backing.bytes_read <= 1024 * 1024 + 64 * 1024


def test_talent_reference_path_traversal_rejected(client):
    img_bytes = _create_test_image("PNG")
    files = {"file": ("ref.png", img_bytes, "image/png")}
    data = {"person_id": "../../etc/shadow", "description": "malicious"}
    res = client.post("/api/v1/assets/upload", files=files, data=data)
    assert res.status_code == 400
    assert "person_id" in res.json()["detail"]
    assert not (client.app.state.root / "data" / "people" / ".." / ".." / "etc" / "shadow").exists()


def test_asset_registration_error_cleans_uploaded_reference(client, monkeypatch):
    monkeypatch.setattr("src.carousel.tools.asset_library.add_asset", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("index unavailable")))
    response = client.post(
        "/api/v1/assets/upload",
        files={"file": ("ref.png", _create_test_image(), "image/png")},
        data={"person_id": "valid_person"},
    )
    assert response.status_code == 500
    assert not (client.app.state.root / "data" / "people" / "valid_person" / "reference.png").exists()


def test_logo_upload_requires_explicit_development_auth_opt_in(client, monkeypatch):
    monkeypatch.setattr("src.core.auth.get_configured_api_key", lambda: "")
    monkeypatch.delenv("ALLOW_UNAUTHENTICATED_DEV", raising=False)
    response = client.post("/api/v1/brand/logo", files={"file": ("logo.png", _create_test_image(), "image/png")})
    assert response.status_code == 503


def test_logo_upload_rejects_invalid_api_key(client, monkeypatch):
    monkeypatch.setattr("src.core.auth.get_configured_api_key", lambda: "expected-key")
    response = client.post(
        "/api/v1/brand/logo",
        headers={"X-API-Key": "wrong-key"},
        files={"file": ("logo.png", _create_test_image(), "image/png")},
    )
    assert response.status_code == 403


def test_logo_upload_accepts_valid_api_key(client, monkeypatch):
    monkeypatch.setattr("src.core.auth.get_configured_api_key", lambda: "expected-key")
    response = client.post(
        "/api/v1/brand/logo",
        headers={"X-API-Key": "expected-key"},
        files={"file": ("logo.png", _create_test_image(), "image/png")},
    )
    assert response.status_code == 200


@pytest.mark.parametrize("method,path,kwargs", [
    ("patch", "/api/v1/strategy/calendar/1", {"json": {"status": "approved"}}),
    ("post", "/api/v1/brand", {"json": {"company": "Changed"}}),
    ("post", "/api/v1/brand/logo", {"files": {"file": ("a.png", _create_test_image(), "image/png")}}),
    ("post", "/api/v1/assets/upload", {"files": {"file": ("a.png", _create_test_image(), "image/png")}, "data": {"person_id": "valid_person"}}),
    ("post", "/api/v1/runs/generate-video", {"json": {"topic": "t"}}),
])
def test_mutation_routes_reject_missing_api_configuration(client, monkeypatch, method, path, kwargs):
    monkeypatch.setattr("src.core.auth.get_configured_api_key", lambda: "")
    monkeypatch.delenv("ALLOW_UNAUTHENTICATED_DEV", raising=False)
    response = getattr(client, method)(path, **kwargs)
    assert response.status_code == 503


def test_cors_does_not_allow_unlisted_origin(client):
    response = client.options(
        "/api/v1/brand",
        headers={
            "Origin": "https://untrusted.invalid",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.headers.get("access-control-allow-origin") != "https://untrusted.invalid"


