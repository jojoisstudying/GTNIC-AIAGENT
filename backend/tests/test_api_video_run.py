"""Regression tests: lifecycle run video (status, event, URL hasil) tanpa jaringan/ffmpeg."""
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src import api, config
from src.core.context import create_run_context
from src.core.db import Base, Design, Event, Run
from src.video.models import VideoRunResult

BRAND = {"company": "Test Brand"}


@pytest.fixture()
def env(tmp_path: Path, monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    out_dir = tmp_path / "output"
    (out_dir / "reels").mkdir(parents=True)
    monkeypatch.setattr(config, "OUTPUT_DIR", out_dir)
    monkeypatch.setattr(api, "SessionLocal", factory)
    monkeypatch.setattr(api.pipeline, "load_brand", lambda: BRAND)
    monkeypatch.setattr(
        api, "create_run_context",
        lambda topic, brand, **kw: create_run_context(topic, brand, session_factory=factory, **kw),
    )

    ctx = create_run_context("topik uji", BRAND, session_factory=factory)
    run_id = ctx.run_id
    ctx.close()
    return factory, out_dir, run_id


def _fake_pipeline(result_or_exc):
    class FakePipeline:
        def __init__(self, context=None, **_):
            self.ctx = context

        async def run_pipeline(self, topic, target_duration_sec=30, out_video_path=None, **_):
            if isinstance(result_or_exc, Exception):
                raise result_or_exc
            Path(out_video_path).write_bytes(b"\x00" * 2048)
            return result_or_exc(out_video_path)

    return FakePipeline


def test_success_marks_run_ok_and_stores_video(env, monkeypatch):
    factory, out_dir, run_id = env
    monkeypatch.setattr(
        "src.video.pipeline.VideoPipeline",
        _fake_pipeline(lambda p: VideoRunResult(
            ok=True, video_path=p, duration_sec=28.5, file_size_mb=3.2, scenes_count=4)),
    )

    api._execute_video_pipeline_task(run_id, "topik uji", 30)

    with factory() as s:
        run = s.get(Run, run_id)
        assert run.status == "ok"
        assert run.finished_at is not None
        design = s.scalars(select(Design).where(Design.run_id == run_id)).one()
        assert design.plan_id is None
        data = json.loads(design.result_json)
        assert data["type"] == "video"
        assert data["video_path"].endswith(f"reels_{run_id}.mp4")
        # event yang di-emit pipeline tidak boleh membuat kolom name kotor
        names = [e.name for e in s.scalars(select(Event).where(Event.run_id == run_id))]
        assert "run_started" in names and "run_finished" in names


def test_get_run_status_exposes_video_url(env, monkeypatch):
    factory, out_dir, run_id = env
    monkeypatch.setattr(
        "src.video.pipeline.VideoPipeline",
        _fake_pipeline(lambda p: VideoRunResult(
            ok=True, video_path=p, duration_sec=20.0, file_size_mb=1.0, scenes_count=3)),
    )
    api._execute_video_pipeline_task(run_id, "topik uji", 30)

    body = api.get_run_status(run_id)
    assert body["format"] == "video"
    assert body["status"] == "ok"
    assert body["video"]["url"] == f"/static/output/reels/reels_{run_id}.mp4"
    assert body["design"] is None


def test_qc_failure_marks_run_failed_with_issues(env, monkeypatch):
    factory, out_dir, run_id = env
    monkeypatch.setattr(
        "src.video.pipeline.VideoPipeline",
        _fake_pipeline(lambda p: VideoRunResult(
            ok=False, video_path=p, issues=["Missing audio stream"], scenes_count=2)),
    )

    api._execute_video_pipeline_task(run_id, "topik uji", 30)

    with factory() as s:
        run = s.get(Run, run_id)
        assert run.status == "failed"
        assert "Missing audio stream" in run.error


def test_script_failure_shows_readable_error_on_run(env, monkeypatch):
    from src.video.scriptwriter import ScriptGenerationError

    factory, out_dir, run_id = env
    msg = "Scriptwriter gagal membuat naskah valid setelah 3 percobaan. Masalah terakhir: Total narasi 12 kata"
    monkeypatch.setattr("src.video.pipeline.VideoPipeline", _fake_pipeline(ScriptGenerationError(msg)))

    api._execute_video_pipeline_task(run_id, "topik uji", 30)

    with factory() as s:
        run = s.get(Run, run_id)
        assert run.status == "failed"
        assert "Scriptwriter gagal" in run.error and "Total narasi" in run.error


def test_video_task_injects_topic_researcher(env, monkeypatch):
    factory, out_dir, run_id = env
    seen = {}

    class SpyPipeline:
        def __init__(self, context=None, researcher=None, **_):
            seen["researcher"] = researcher

        async def run_pipeline(self, topic, target_duration_sec=30, out_video_path=None, **_):
            raise RuntimeError("stop")

    monkeypatch.setattr("src.video.pipeline.VideoPipeline", SpyPipeline)
    api._execute_video_pipeline_task(run_id, "topik uji", 30)
    assert callable(seen["researcher"])


def test_exception_marks_run_failed_instead_of_stuck_running(env, monkeypatch):
    factory, out_dir, run_id = env
    monkeypatch.setattr("src.video.pipeline.VideoPipeline", _fake_pipeline(RuntimeError("boom")))

    api._execute_video_pipeline_task(run_id, "topik uji", 30)

    with factory() as s:
        run = s.get(Run, run_id)
        assert run.status == "failed"
        assert "boom" in run.error
        err = s.scalars(select(Event).where(Event.run_id == run_id, Event.kind == "error")).one()
        assert err.name == "video_pipeline"
        assert json.loads(err.detail_json)["error"] == "boom"