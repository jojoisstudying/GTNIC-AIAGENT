"""API: publish Reels, saran caption + status publikasi di GET run, dan checkbox riset video."""
import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src import api, config
from src.core.context import create_run_context
from src.core.db import Base, Publication

BRAND = {"company": "Test Brand", "hashtags": ["#tes"]}
VIDEO = {"type": "video", "ok": True, "video_path": None, "duration_sec": 19.3,
         "file_size_mb": 4.2, "scenes_count": 3, "issues": []}


@pytest.fixture()
def env(tmp_path: Path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    out_dir = tmp_path / "output"
    (out_dir / "reels").mkdir(parents=True)
    monkeypatch.setattr(config, "OUTPUT_DIR", out_dir)
    monkeypatch.setattr(api, "SessionLocal", factory)
    monkeypatch.setattr(api.pipeline, "load_brand", lambda: BRAND)
    monkeypatch.setattr(api, "create_run_context",
                        lambda topic, brand, **kw: create_run_context(topic, brand, session_factory=factory, **kw))

    ctx = create_run_context("Apa itu HTTPS", BRAND, session_factory=factory)
    run_id = ctx.run_id
    ctx.close()
    video = {**VIDEO, "video_path": str(out_dir / "reels" / f"reels_{run_id}.mp4")}
    api._save_video_result(run_id, video, "ok")
    return factory, run_id, video


def test_publish_video_run_sends_edited_caption_to_publisher(env, monkeypatch):
    factory, run_id, video = env
    seen = {}
    monkeypatch.setattr("src.agents.publisher.preflight_video",
                        lambda v, caption, run_id=None, session=None, ctx=None: seen.update(pre=(v["video_path"], caption, run_id)) or [])
    monkeypatch.setattr("src.agents.publisher.publish_reel",
                        lambda path, caption, share_to_feed=True, ctx=None: seen.update(pub=(path, caption, share_to_feed))
                        or {"media_id": "IG1", "permalink": "https://instagr.am/reel/1"})

    res = api.publish_run_to_instagram(run_id, api.PublishOptions(caption="Caption editan #tes", share_to_feed=False))

    assert res["format"] == "reel" and res["status"] == "published" and res["media_id"] == "IG1"
    assert seen["pub"] == (video["video_path"], "Caption editan #tes", False)
    assert seen["pre"][1] == "Caption editan #tes" and seen["pre"][2] == run_id


def test_publish_without_body_uses_default_caption(env, monkeypatch):
    _, run_id, _ = env
    seen = {}
    monkeypatch.setattr("src.agents.publisher.preflight_video", lambda *a, **k: [])
    monkeypatch.setattr("src.agents.publisher.publish_reel",
                        lambda path, caption, share_to_feed=True, ctx=None: seen.update(c=caption, f=share_to_feed) or {"media_id": "IG2"})
    api.publish_run_to_instagram(run_id)
    assert seen["c"].startswith("Apa itu HTTPS") and "#tes" in seen["c"] and seen["f"] is True


def test_preflight_problems_become_400_and_nothing_is_published(env, monkeypatch):
    _, run_id, _ = env
    monkeypatch.setattr("src.agents.publisher.preflight_video", lambda *a, **k: ["durasi 2.0 detik di luar batas", "caption kosong"])
    monkeypatch.setattr("src.agents.publisher.publish_reel", lambda *a, **k: pytest.fail("tidak boleh posting"))
    with pytest.raises(HTTPException) as exc:
        api.publish_run_to_instagram(run_id, api.PublishOptions(caption=""))
    assert exc.value.status_code == 400 and "durasi" in exc.value.detail and "caption kosong" in exc.value.detail


def test_publisher_error_becomes_500_with_readable_message(env, monkeypatch):
    _, run_id, _ = env
    monkeypatch.setattr("src.agents.publisher.preflight_video", lambda *a, **k: [])

    def boom(*a, **k):
        raise RuntimeError("Container C1 berstatus ERROR")
    monkeypatch.setattr("src.agents.publisher.publish_reel", boom)
    with pytest.raises(HTTPException) as exc:
        api.publish_run_to_instagram(run_id, api.PublishOptions(caption="c"))
    assert exc.value.status_code == 500 and "berstatus ERROR" in exc.value.detail


def test_get_run_exposes_suggested_caption_and_persisted_publication(env):
    factory, run_id, _ = env
    res = api.get_run_status(run_id)
    assert res["video"]["suggested_caption"].startswith("Apa itu HTTPS")
    assert res["publication"] is None

    with factory() as s:
        s.add(Publication(run_id=run_id, status="published", media_id="IG9",
                          permalink="https://instagr.am/reel/9", caption="c", image_urls_json="[]"))
        s.commit()
    res = api.get_run_status(run_id)
    assert res["publication"] == {"status": "published", "media_id": "IG9",
                                  "permalink": "https://instagr.am/reel/9", "error": None}


def test_video_checkbox_off_uses_cache_only_and_on_runs_live(env, monkeypatch):
    _, run_id, _ = env
    seen = {}

    class SpyPipeline:
        def __init__(self, context=None, researcher=None, **_):
            seen["researcher"] = researcher

        async def run_pipeline(self, topic, **_):
            raise RuntimeError("stop")

    monkeypatch.setattr("src.video.pipeline.VideoPipeline", SpyPipeline)
    live_calls = []
    monkeypatch.setattr("src.video.topic_research.gather_topic_research",
                        lambda topic, ctx=None, **k: live_calls.append(topic) or {"ok": True, "context": "x", "sources": []})

    api._execute_video_pipeline_task(run_id, "topik tanpa cache", 30, False)
    res = seen["researcher"]("topik tanpa cache")
    assert res["ok"] is False and "Riset live dimatikan" in res["error"] and live_calls == []

    api._execute_video_pipeline_task(run_id, "topik live", 30, True)
    assert seen["researcher"]("topik live")["ok"] is True and live_calls == ["topik live"]


def test_video_request_defaults_to_live_research():
    assert api.VideoRunRequest(topic="t").fresh is True
    assert api.VideoRunRequest(topic="t", fresh=False).fresh is False
