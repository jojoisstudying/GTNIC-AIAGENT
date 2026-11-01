"""instagram.publish_reel & wait_until_ready(with_detail): tanpa jaringan."""
import pytest

from src.tools import instagram


@pytest.fixture(autouse=True)
def no_sleep_no_env(monkeypatch):
    monkeypatch.setattr(instagram.time, "sleep", lambda s: None)
    monkeypatch.setattr(instagram.config, "need", lambda name: "UID123")


def test_publish_reel_creates_reels_container_waits_then_publishes(monkeypatch):
    posts, gets = [], []
    monkeypatch.setattr(instagram, "_post", lambda path, ctx=None, **d: posts.append((path, d)) or {"id": "C1" if len(posts) == 1 else "M9"})
    states = iter(["IN_PROGRESS", "IN_PROGRESS", "FINISHED"])
    monkeypatch.setattr(instagram, "_get", lambda path, ctx=None, **p: gets.append((path, p)) or {"status_code": next(states)})

    media_id = instagram.publish_reel("https://cdn.test/v.mp4", "Caption #tes")

    assert media_id == "M9"
    path, data = posts[0]
    assert path == "UID123/media"
    assert data == {"media_type": "REELS", "video_url": "https://cdn.test/v.mp4",
                    "caption": "Caption #tes", "share_to_feed": "true"}
    assert posts[1] == ("UID123/media_publish", {"creation_id": "C1"})
    assert len(gets) == 3 and gets[0][1]["fields"] == "status_code,status"


def test_share_to_feed_can_be_disabled(monkeypatch):
    posts = []
    monkeypatch.setattr(instagram, "_post", lambda path, ctx=None, **d: posts.append(d) or {"id": "X"})
    monkeypatch.setattr(instagram, "_get", lambda *a, **k: {"status_code": "FINISHED"})
    instagram.publish_reel("https://cdn.test/v.mp4", "c", share_to_feed=False)
    assert posts[0]["share_to_feed"] == "false"


def test_error_status_includes_meta_detail_for_reels(monkeypatch):
    monkeypatch.setattr(instagram, "_get", lambda *a, **k: {"status_code": "ERROR", "status": "Error: video codec tidak didukung"})
    with pytest.raises(RuntimeError) as exc:
        instagram.wait_until_ready("C1", with_detail=True)
    assert "ERROR" in str(exc.value) and "codec tidak didukung" in str(exc.value)


def test_default_wait_keeps_old_behaviour(monkeypatch):
    seen = {}
    monkeypatch.setattr(instagram, "_get", lambda path, ctx=None, **p: seen.update(p) or {"status_code": "FINISHED"})
    instagram.wait_until_ready("C1")
    assert seen == {"fields": "status_code"}


def test_timeout_raises(monkeypatch):
    monkeypatch.setattr(instagram, "_get", lambda *a, **k: {"status_code": "IN_PROGRESS"})
    with pytest.raises(RuntimeError, match="belum siap"):
        instagram.wait_until_ready("C1", timeout=6, interval=3)
