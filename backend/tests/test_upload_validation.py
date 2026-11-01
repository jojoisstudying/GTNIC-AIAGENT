"""Tests for file validation and path traversal security on asset/logo uploads (BUG-06)."""
import io
import pytest
from fastapi.testclient import TestClient
from fastapi import UploadFile, HTTPException
from PIL import Image

from src.api import app, _validate_image_file


@pytest.fixture()
def client():
    return TestClient(app)


def _create_test_image(format="PNG", size=(100, 100), color="blue"):
    buf = io.BytesIO()
    im = Image.new("RGB", size, color=color)
    im.save(buf, format=format)
    buf.seek(0)
    return buf.getvalue()


def test_valid_logo_upload(client):
    img_bytes = _create_test_image("PNG")
    files = {"file": ("logo.png", img_bytes, "image/png")}
    res = client.post("/api/v1/brand/logo", files=files)
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_invalid_image_corrupt_rejected(client):
    files = {"file": ("corrupt.png", b"NOT_A_VALID_IMAGE_HEADER_12345", "image/png")}
    res = client.post("/api/v1/brand/logo", files=files)
    assert res.status_code == 400
    assert "tidak valid" in res.json()["detail"].lower()


def test_empty_file_rejected(client):
    files = {"file": ("empty.png", b"", "image/png")}
    res = client.post("/api/v1/brand/logo", files=files)
    assert res.status_code == 400
    assert "kosong" in res.json()["detail"].lower()


def test_oversized_file_rejected():
    fake_file = UploadFile(filename="huge.png", file=io.BytesIO(b"X" * (6 * 1024 * 1024)))
    with pytest.raises(HTTPException) as exc:
        _validate_image_file(fake_file, max_mb=5.0)
    assert exc.value.status_code == 400
    assert "melebihi batas" in exc.value.detail


def test_talent_reference_path_traversal_rejected(client):
    img_bytes = _create_test_image("PNG")
    files = {"file": ("ref.png", img_bytes, "image/png")}
    data = {"person_id": "../../etc/shadow", "description": "malicious"}
    res = client.post("/api/v1/assets/upload", files=files, data=data)
    assert res.status_code == 400
    assert "person_id" in res.json()["detail"]
