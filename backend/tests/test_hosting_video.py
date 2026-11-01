"""hosting.upload_video: URL publik .mp4 untuk Reels (Cloudinary disimulasikan)."""
import sys
import types

import pytest

from src.tools import hosting


@pytest.fixture(autouse=True)
def fake_cloudinary(monkeypatch):
    cl = types.ModuleType("cloudinary")
    up = types.ModuleType("cloudinary.uploader")
    ut = types.ModuleType("cloudinary.utils")
    ut.api_sign_request = lambda params, secret: "SIG"
    cl.uploader, cl.utils, cl.config = up, ut, lambda **k: None
    monkeypatch.setitem(sys.modules, "cloudinary", cl)
    monkeypatch.setitem(sys.modules, "cloudinary.uploader", up)
    monkeypatch.setitem(sys.modules, "cloudinary.utils", ut)
    for k in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"):
        monkeypatch.setenv(k, "x")
    return up


class FakeHttp:
    def __init__(self, payload):
        self.payload, self.calls = payload, []

    def request(self, method, url, **kw):
        self.calls.append((method, url, kw))
        payload = self.payload

        class R:
            def json(self_inner):
                return payload
        return R()


def _video(tmp_path):
    p = tmp_path / "reels_abc.mp4"
    p.write_bytes(b"\x00" * 2048)
    return str(p)


def test_signed_upload_goes_to_video_endpoint_and_returns_mp4_url(tmp_path):
    http = FakeHttp({"secure_url": "https://res.cloudinary.com/demo/video/upload/v1/gtnic-reels/reels_abc_1.mp4"})
    url = hosting.upload_video(_video(tmp_path), http=http)
    method, endpoint, kw = http.calls[0]
    assert method == "POST" and endpoint.endswith("/x/video/upload")
    assert kw["data"]["folder"] == "gtnic-reels" and kw["data"]["signature"] == "SIG"
    assert kw["files"]["file"][2] == "video/mp4"
    assert url.endswith(".mp4")


def test_url_without_video_extension_is_forced_to_mp4(tmp_path):
    http = FakeHttp({"secure_url": "https://res.cloudinary.com/demo/video/upload/v1/gtnic-reels/reels_abc_1"})
    assert hosting.upload_video(_video(tmp_path), http=http).endswith("reels_abc_1.mp4")
    http = FakeHttp({"secure_url": "https://res.cloudinary.com/demo/video/upload/v1/x/clip.webm?_a=1"})
    assert hosting.upload_video(_video(tmp_path), http=http).endswith("clip.mp4")


def test_mov_is_kept(tmp_path):
    http = FakeHttp({"secure_url": "https://res.cloudinary.com/demo/video/upload/v1/x/clip.mov"})
    assert hosting.upload_video(_video(tmp_path), http=http).endswith("clip.mov")


def test_cloudinary_error_becomes_readable_exception(tmp_path):
    http = FakeHttp({"error": {"message": "File size too large. Got 120000000. Maximum is 104857600."}})
    with pytest.raises(RuntimeError, match="File size too large"):
        hosting.upload_video(_video(tmp_path), http=http)
