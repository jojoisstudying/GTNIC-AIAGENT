"""Publisher Reels: preflight, idempotensi intent -> published/failed, tanpa jaringan."""
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from src.agents import publisher
from src.core.db import Base, Publication

VIDEO = {"type": "video", "ok": True, "video_path": "reels_run1.mp4", "issues": []}
URL = "https://cdn.example.com/reels_run1.mp4"


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


class Ctx:
    def __init__(self, session, run_id="run-reel-1"):
        self.session, self.run_id, self.http, self.events = session, run_id, None, []

    def emit(self, kind, name, **fields):
        self.events.append((kind, name, fields))


@pytest.fixture(autouse=True)
def isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(publisher, "PUBLISHED_FILE", tmp_path / "published.json")
    monkeypatch.setattr(publisher, "ensure_instagram_credentials", lambda *a, **k: None)
    monkeypatch.setattr(publisher, "check_publishing_quota", lambda ctx=None: {})
    monkeypatch.setattr("src.video.reel_check.check_reel_compat", lambda path: [])
    for k in publisher.REQUIRED_ENV:
        monkeypatch.setenv(k, "x")


def test_default_caption_uses_topic_and_brand_hashtags():
    cap = publisher.default_video_caption("Apa itu HTTPS", {"hashtags": ["web", "#keamanan"]})
    assert cap.startswith("Apa itu HTTPS") and cap.endswith("#web #keamanan")
    assert publisher.default_video_caption("T", {}) .count("#") == 0


def test_preflight_ok(test_db):
    s = test_db()
    assert publisher.preflight_video(VIDEO, "Caption #a", run_id="run-reel-1", session=s) == []


def test_preflight_reports_each_problem(test_db, monkeypatch):
    s = test_db()
    monkeypatch.setattr("src.video.reel_check.check_reel_compat", lambda p: ["codec video 'vp9' tidak didukung"])
    problems = publisher.preflight_video({**VIDEO, "ok": False, "issues": ["Missing audio"]},
                                         "", run_id="r", session=s)
    joined = " | ".join(problems)
    assert "belum lolos QC" in joined and "codec video" in joined and "caption kosong" in joined

    too_long = publisher.preflight_video(VIDEO, "x" * 2201, session=s)
    assert any("2200" in p for p in too_long)
    many_tags = publisher.preflight_video(VIDEO, " ".join(f"#t{i}" for i in range(31)), session=s)
    assert any("30 hashtag" in p for p in many_tags)

    monkeypatch.delenv("IG_TOKEN")
    assert any("env belum diisi" in p for p in publisher.preflight_video(VIDEO, "ok", session=s))


def test_preflight_blocks_second_publish_of_same_run(test_db):
    s = test_db()
    s.add(Publication(run_id="run-reel-1", status="published", media_id="IG1", caption="c", image_urls_json="[]"))
    s.commit()
    problems = publisher.preflight_video(VIDEO, "ok", run_id="run-reel-1", session=s)
    assert any("sudah dipublish" in p and "IG1" in p for p in problems)


def test_publish_reel_writes_intent_then_published(test_db, monkeypatch):
    s = test_db()
    calls = {}
    monkeypatch.setattr("src.tools.hosting.upload_video", lambda p, http=None: URL)
    monkeypatch.setattr("src.tools.instagram.publish_reel",
                        lambda url, cap, share_to_feed=True, ctx=None: calls.update(url=url, cap=cap, feed=share_to_feed) or "IGREEL1")
    monkeypatch.setattr("src.tools.instagram.get_media_metrics", lambda mid, ctx=None: {"permalink": "https://instagr.am/reel/1"})
    ctx = Ctx(s)

    rec = publisher.publish_reel("reels_run1.mp4", "  Caption Reels  ", on_step=lambda *_: None,
                                 share_to_feed=False, ctx=ctx)

    assert rec["media_id"] == "IGREEL1" and rec["format"] == "reel" and rec["video_url"] == URL
    assert calls == {"url": URL, "cap": "Caption Reels", "feed": False}
    pub = s.scalar(select(Publication).where(Publication.run_id == "run-reel-1"))
    assert pub.status == "published" and pub.permalink == "https://instagr.am/reel/1"
    assert json.loads(pub.image_urls_json) == [URL]
    names = [e[1] for e in ctx.events]
    assert names == ["publication_intent", "publication_published"]
    assert ctx.events[0][2]["detail"]["format"] == "reel"
    assert json.loads(publisher.PUBLISHED_FILE.read_text())[0]["media_id"] == "IGREEL1"
    assert pub.published_at is not None
    assert pub.scheduled_for is None


def test_publish_reel_failure_marks_row_failed_and_reraises(test_db, monkeypatch):
    s = test_db()
    monkeypatch.setattr("src.tools.hosting.upload_video", lambda p, http=None: URL)

    def boom(*a, **k):
        raise RuntimeError("Container C1 berstatus ERROR: video codec tidak didukung")
    monkeypatch.setattr("src.tools.instagram.publish_reel", boom)
    ctx = Ctx(s)

    with pytest.raises(RuntimeError, match="codec tidak didukung"):
        publisher.publish_reel("reels_run1.mp4", "c", on_step=lambda *_: None, ctx=ctx)

    pub = s.scalar(select(Publication).where(Publication.run_id == "run-reel-1"))
    assert pub.status == "failed" and "codec tidak didukung" in pub.error
    assert ctx.events[-1][1] == "publication_failed"


def test_upload_failure_leaves_no_intent_row(test_db, monkeypatch):
    s = test_db()

    def boom(p, http=None):
        raise RuntimeError("Upload video ke Cloudinary gagal")
    monkeypatch.setattr("src.tools.hosting.upload_video", boom)
    with pytest.raises(RuntimeError, match="Cloudinary"):
        publisher.publish_reel("reels_run1.mp4", "c", on_step=lambda *_: None, ctx=Ctx(s))
    assert s.scalar(select(Publication)) is None   # belum ada niat posting -> tidak ada intent menggantung


def test_hanging_intent_blocks_reel_publish(test_db, monkeypatch):
    s = test_db()
    s.add(Publication(run_id="run-old", status="intent", intent_at=datetime.now(timezone.utc),
                      caption="c", image_urls_json="[]"))
    s.commit()
    monkeypatch.setattr("src.tools.hosting.upload_video", lambda p, http=None: pytest.fail("jangan upload"))
    with pytest.raises(publisher.PendingIntentError):
        publisher.publish_reel("reels_run1.mp4", "c", on_step=lambda *_: None, ctx=Ctx(s))
