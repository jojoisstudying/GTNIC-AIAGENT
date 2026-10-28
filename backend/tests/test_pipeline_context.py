"""Integration test for run-scoped pipeline persistence without network access."""
import json
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from src import config
from src.carousel import pipeline
from src.core.context import create_run_context
from src.core.db import Base, Design, Event, Plan, ResearchSnapshot, Run
from src.core.events import EventEmitter
from src.core.http import HttpClient
from src.core.llm import LLMClient


def test_pipeline_persists_research_plan_design_and_events(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path
    (root / "config").mkdir()
    (root / "output").mkdir()
    brand = {
        "company": "Test Brand", "industry": "manufacturing", "description": "test",
        "audience": "workers", "tone": "clear", "content_pillars": [], "rules": [],
        "available_poses": [], "colors": {"primary": "#0B2A5B", "secondary": "#EAF1FF",
        "accent": "#FFB400", "text_on_primary": "#FFFFFF"},
    }
    (root / "config" / "brand.json").write_text(json.dumps(brand), encoding="utf-8")
    engine = create_engine(f"sqlite:///{root / 'test.db'}")
    from src.core.db import Base
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    emitter = EventEmitter("pending", factory, lambda _message: None)
    context = create_run_context("test topic", brand, session_factory=factory)

    research = {"sources": [], "posting_time": {}}
    plan = {"format": "single_image", "slides": [{"role": "single", "headline": "Test", "subtext": ""}],
            "caption": "Test", "hashtags": ["#test"], "schedule": {"slots": [], "ab_test": ""}}
    design_result = {"ok": True, "slides": [], "warnings": [], "preview": str(root / "output" / "preview.jpg"),
                     "pending_review": []}
    monkeypatch.setattr(pipeline, "load_brand", lambda: brand)
    monkeypatch.setattr(pipeline, "load_saved_research", lambda: research)
    monkeypatch.setattr(pipeline.planner, "run", lambda *args, **kwargs: {"ok": True, "plan": plan, "issues": []})
    monkeypatch.setattr(pipeline.designer, "run", lambda *args, **kwargs: design_result)
    monkeypatch.setattr(config, "OUTPUT_DIR", root / "output")
    context.emitter = EventEmitter(context.run_id, factory, lambda _message: None)

    result = pipeline.run("test topic", fresh=False, ctx=context, include_design=True)
    assert result["design"] is design_result

    with factory() as session:
        assert session.get(Run, context.run_id).status == "ok"
        assert session.scalar(select(ResearchSnapshot).where(ResearchSnapshot.run_id == context.run_id)) is not None
        assert session.scalar(select(Plan).where(Plan.run_id == context.run_id)) is not None
        assert session.scalar(select(Design).where(Design.run_id == context.run_id)) is not None
        assert session.scalar(select(Event).where(Event.run_id == context.run_id)) is not None
    context.close()
    engine.dispose()


def test_create_run_context_reuses_existing_run(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'existing-run.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    brand = {"company": "Test Brand"}
    run_id = "existing-run-id"

    with factory() as session:
        session.add(Run(id=run_id, topic="resume topic", brand_id="Test Brand", status="awaiting_assets"))
        session.commit()

    context = create_run_context("resume topic", brand, run_id=run_id, session_factory=factory)
    assert context.run_id == run_id

    with factory() as session:
        runs = session.scalars(select(Run)).all()
        assert len(runs) == 1
        assert runs[0].id == run_id
        assert runs[0].status == "awaiting_assets"

    context.emitter.printer = lambda _message: None
    context.emit("info", "resume_context_test")
    with factory() as session:
        event = session.scalar(select(Event).where(Event.name == "resume_context_test"))
        assert event is not None
        assert event.run_id == run_id

    context.close()
    engine.dispose()
