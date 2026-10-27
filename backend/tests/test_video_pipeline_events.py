"""Regression: event VideoPipeline harus tersimpan (name bersih, payload di detail)."""
import json
from unittest.mock import MagicMock

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.context import create_run_context
from src.core.db import Base, Event
from src.video.pipeline import VideoPipeline


def _ctx():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return create_run_context("topik uji", {"company": "T"}, session_factory=factory), factory


def test_emit_persists_clean_name_and_detail():
    ctx, factory = _ctx()
    vp = VideoPipeline(scriptwriter=MagicMock(), broll_fetcher=MagicMock(), context=ctx)

    vp._emit("video_pipeline_started", {"topic": "x", "target_duration_sec": 15})
    vp._emit("video_pipeline_finished", {"ok": False}, status="failed")

    with factory() as s:
        rows = s.scalars(select(Event).where(Event.run_id == ctx.run_id).order_by(Event.id)).all()
    assert [r.name for r in rows] == ["video_pipeline_started", "video_pipeline_finished"]
    assert rows[0].kind == "info" and rows[0].step == "video"
    assert json.loads(rows[0].detail_json) == {"topic": "x", "target_duration_sec": 15}
    assert rows[1].status == "failed"


def test_default_scriptwriter_shares_run_llm_for_cost_tracking():
    ctx, _ = _ctx()
    vp = VideoPipeline(broll_fetcher=MagicMock(), context=ctx)
    assert vp.scriptwriter.llm is ctx.llm