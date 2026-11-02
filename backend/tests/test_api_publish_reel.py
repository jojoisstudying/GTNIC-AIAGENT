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
from src.core.db import Base, Publication, PostAnalytics, ContentStrategyItem, ingest_publication_metrics, utc_now

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
    with factory() as session:
        session.add(ContentStrategyItem(
            plan_date="2026-11-03", topic="Apa itu HTTPS", format="video", content_pillar="Edukasi",
            objective="Edukasi", target_segment="Umum", scheduled_slot="09:00",
            status="approved", run_id=run_id,
        ))
        session.commit()
    return factory, run_id, video


def test_publish_video_run_sends_edited_caption_to_publisher(env, monkeypatch):
    factory, run_id, video = env
    seen = {}
    monkeypatch.setattr("src.agents.publisher.preflight_video",
                        lambda v, caption, run_id=None, session=None, ctx=None: seen.update(pre=(v["video_path"], caption, run_id)) or [])
    def publish_reel(path, caption, share_to_feed=True, ctx=None):
        seen["pub"] = (path, caption, share_to_feed)
        with factory() as session:
            session.add(Publication(
                run_id=run_id, status="published", media_id="IG1",
                    permalink="https://instagr.am/reel/1", caption=caption, image_urls_json="[]", published_at=utc_now(),
            ))
            session.commit()
        return {"media_id": "IG1", "permalink": "https://instagr.am/reel/1"}

    monkeypatch.setattr("src.agents.publisher.publish_reel", publish_reel)

    res = api.publish_run_to_instagram(run_id, api.PublishOptions(caption="Caption editan #tes", share_to_feed=False))

    assert res["format"] == "reel" and res["status"] == "published" and res["media_id"] == "IG1"
    assert seen["pub"] == (video["video_path"], "Caption editan #tes", False)
    assert seen["pre"][1] == "Caption editan #tes" and seen["pre"][2] == run_id
    with factory() as session:
        analytics = session.query(PostAnalytics).one()
        publication = session.query(Publication).one()
        assert analytics.publication_id == publication.id
        assert analytics.run_id == run_id
        assert analytics.media_id == "IG1"
        assert analytics.reach is None
        assert analytics.ingestion_status == "pending"
        assert analytics.strategy_item_id == session.query(ContentStrategyItem).filter_by(run_id=run_id).one().id
        assert publication.published_at is not None
        assert publication.scheduled_for is None


def test_analytics_tracking_is_idempotent_for_publication(env, monkeypatch):
    factory, run_id, video = env
    with factory() as session:
        session.add(Publication(run_id=run_id, status="published", media_id="IG1", caption="c", image_urls_json="[]"))
        session.commit()
    monkeypatch.setattr("src.agents.publisher.preflight_video", lambda *a, **k: [])
    monkeypatch.setattr("src.agents.publisher.publish_reel", lambda *a, **k: {"media_id": "IG1"})
    with pytest.raises(HTTPException) as exc:
        api.publish_run_to_instagram(run_id)
    assert exc.value.status_code == 409
    with factory() as session:
        assert session.query(PostAnalytics).count() == 0


def test_analytics_persistence_failure_is_not_silently_hidden(env, monkeypatch):
    factory, run_id, _ = env
    monkeypatch.setattr("src.agents.publisher.preflight_video", lambda *a, **k: [])
    monkeypatch.setattr("src.agents.publisher.publish_reel", lambda *a, **k: {"media_id": "IG1"})
    calls = 0
    def failing_session_factory():
        nonlocal calls
        calls += 1
        if calls == 3:
            raise RuntimeError("analytics DB unavailable")
        return factory()
    monkeypatch.setattr(api, "SessionLocal", failing_session_factory)
    with pytest.raises(HTTPException) as exc:
        api.publish_run_to_instagram(run_id)
    assert exc.value.status_code == 500
    assert "analytics DB unavailable" in exc.value.detail


def test_analytics_ingestion_is_idempotent_and_preserves_missing_metrics(env):
    factory, run_id, _ = env
    with factory() as session:
        publication = Publication(run_id=run_id, status="published", media_id="IG_METRICS",
                                  caption="c", image_urls_json="[]")
        session.add(publication)
        session.commit()
        first = ingest_publication_metrics(session, publication, {"likes": 0}, source="test_api")
        session.commit()
        second = ingest_publication_metrics(session, publication, {"likes": 10}, source="test_api")
        session.commit()
        assert first.id == second.id
        assert second.likes == 10
        assert second.reach is None
        assert second.ingestion_status == "complete"
        assert second.source == "test_api"
        assert second.data_timestamp is not None
        assert session.query(PostAnalytics).filter_by(publication_id=publication.id).count() == 1


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


def test_unapproved_strategy_item_cannot_be_published(env):
    factory, run_id, _ = env
    with factory() as session:
        item = session.query(ContentStrategyItem).filter_by(run_id=run_id).one()
        item.status = "draft"
        session.commit()
    with pytest.raises(HTTPException) as exc:
        api.publish_run_to_instagram(run_id)
    assert exc.value.status_code == 409


def test_failed_qc_video_cannot_be_published(env):
    factory, run_id, _ = env
    with factory() as session:
        design = session.query(api.Design).filter_by(run_id=run_id).one()
        payload = json.loads(design.result_json)
        payload["ok"] = False
        design.result_json = json.dumps(payload)
        session.commit()
    with pytest.raises(HTTPException) as exc:
        api.publish_run_to_instagram(run_id)
    assert exc.value.status_code == 409


def test_failed_run_cannot_be_approved(env):
    factory, run_id, _ = env
    with factory() as session:
        run = session.get(api.Run, run_id)
        run.status = "qc_failed"
        item = session.query(ContentStrategyItem).filter_by(run_id=run_id).one()
        item.status = "draft"
        session.commit()
        item_id = session.query(ContentStrategyItem).one().id
    with pytest.raises(HTTPException) as exc:
        api.update_strategy_item_endpoint(item_id, api.StrategyItemAction(status="approved"))
    assert exc.value.status_code == 409


def test_approved_strategy_item_can_publish_and_advances_state(env, monkeypatch):
    factory, run_id, video = env
    with factory() as session:
        item = session.query(ContentStrategyItem).filter_by(run_id=run_id).one()
        item.status = "approved"
        session.commit()
    monkeypatch.setattr("src.agents.publisher.preflight_video", lambda *a, **k: [])

    def publish(path, caption, share_to_feed=True, ctx=None):
        with factory() as session:
            session.add(Publication(run_id=run_id, status="published", media_id="IG_APPROVED",
                                    caption=caption, image_urls_json="[]"))
            session.commit()
        return {"media_id": "IG_APPROVED"}

    monkeypatch.setattr("src.agents.publisher.publish_reel", publish)
    result = api.publish_run_to_instagram(run_id)
    assert result["status"] == "published"
    with factory() as session:
        item = session.query(ContentStrategyItem).one()
        assert item.status == "published"
        analytics = session.query(PostAnalytics).one()
        assert analytics.strategy_item_id == item.id


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

    monkeypatch.setattr("src.reels.pipeline.VideoPipeline", SpyPipeline)
    live_calls = []
    monkeypatch.setattr("src.reels.agents.topic_research.gather_topic_research",
                        lambda topic, ctx=None, **k: live_calls.append(topic) or {"ok": True, "context": "x", "sources": []})

    api._execute_video_pipeline_task(run_id, "topik tanpa cache", 30, False)
    res = seen["researcher"]("topik tanpa cache")
    assert res["ok"] is False and "Riset live dimatikan" in res["error"] and live_calls == []

    api._execute_video_pipeline_task(run_id, "topik live", 30, True)
    assert seen["researcher"]("topik live")["ok"] is True and live_calls == ["topik live"]


def test_video_request_defaults_to_live_research():
    assert api.VideoRunRequest(topic="t").fresh is True
    assert api.VideoRunRequest(topic="t", fresh=False).fresh is False
