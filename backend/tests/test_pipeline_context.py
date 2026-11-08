"""Integration test for run-scoped pipeline persistence without network access."""
import json
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from src import config
from src.carousel import pipeline
from src.core.context import create_run_context
from src.core.db import Base, Design, EnterpriseProfile, EnterpriseProfileVersion, Event, Plan, ResearchSnapshot, Run
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

    with factory() as session:
        profile = EnterpriseProfile(
            company_name="Test Profile", industry="test", description="test",
            products_services_json='[{"name":"Product"}]', target_audience_json='{"primary_segment":"Audience"}',
            business_goals_json='["Goal"]', content_pillars_json='["Pillar"]', brand_rules_json='["No claims"]',
            contact_info_json='{"email":"contact@example.test"}', approval_workflow_json='{"default_mode":"manual_review"}',
            operating_preferences_json='{"timezone":"Asia/Jakarta"}',
        )
        session.add(profile)
        session.commit()
        profile_id = profile.id

    context.brand.update({"enterprise_profile_id": profile_id, "enterprise_profile_updated_at": "v1"})

    result = pipeline.run("test topic", fresh=False, ctx=context, include_design=True)
    assert result["design"] is design_result

    with factory() as session:
        assert session.get(Run, context.run_id).status == "ok"
        assert session.scalar(select(ResearchSnapshot).where(ResearchSnapshot.run_id == context.run_id)) is not None
        assert session.scalar(select(Plan).where(Plan.run_id == context.run_id)) is not None
        assert session.scalar(select(Design).where(Design.run_id == context.run_id)) is not None
        design_row = session.scalar(select(Design).where(Design.run_id == context.run_id))
        assert json.loads(design_row.semantic_qc_json)["ok"] is True
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


def test_load_brand_propagates_complete_enterprise_context(tmp_path: Path, monkeypatch) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'brand-context.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        profile = EnterpriseProfile(
            company_name="Canonical Co", industry="AI", description="Description",
            products_services_json='[{"name":"Product"}]', target_audience_json='{"primary_segment":"CTO"}',
            business_goals_json='["Goal"]', content_pillars_json='["Pillar"]', brand_rules_json='["No unsupported claims"]',
            contact_info_json='{"email":"hello@example.test"}', approval_workflow_json='{"default_mode":"manual_review"}',
            operating_preferences_json='{"timezone":"Asia/Jakarta"}',
        )
        session.add(profile)
        session.commit()
        expected_id = profile.id

    monkeypatch.setattr("src.core.db.SessionLocal", factory)
    monkeypatch.setattr(config, "ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "brand.json").write_text("{}", encoding="utf-8")
    brand = pipeline.load_brand()
    assert brand["enterprise_profile_id"] == expected_id
    assert brand["contact_info"]["email"] == "hello@example.test"
    assert brand["approval_workflow"]["default_mode"] == "manual_review"
    assert brand["operating_preferences"]["timezone"] == "Asia/Jakarta"
    assert brand["products_services"][0]["name"] == "Product"
    context = create_run_context("profile-context", brand, session_factory=factory)
    assert context.enterprise_context["products_services"][0]["name"] == "Product"
    assert context.enterprise_context["business_goals"] == ["Goal"]
    with factory() as session:
        run = session.get(Run, context.run_id)
        assert run.enterprise_profile_id == expected_id
        assert run.enterprise_profile_version == brand["enterprise_profile_updated_at"]
    context.close()
    with factory() as session:
        version = session.query(EnterpriseProfileVersion).filter_by(profile_id=expected_id).one()
        assert json.loads(version.snapshot_json)["contact_info"]["email"] == "hello@example.test"
    engine.dispose()


def test_semantic_qc_failure_prevents_design_and_approval(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path
    (root / "output").mkdir()
    engine = create_engine(f"sqlite:///{root / 'qc-failure.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    brand = {"company": "Test", "industry": "IT"}
    ctx = create_run_context("test topic", brand, session_factory=factory)
    plan = {"format": "carousel", "slides": [
        {"role": "cover", "headline": "Cover"},
        {"role": "content", "headline": "Content"},
        {"role": "cta", "headline": "CTA"},
    ], "caption": "caption", "hashtags": []}
    monkeypatch.setattr(pipeline, "load_brand", lambda: brand)
    monkeypatch.setattr(pipeline, "load_saved_research", lambda: {"sources": []})
    monkeypatch.setattr(pipeline.planner, "run", lambda *a, **k: {"ok": True, "plan": plan, "issues": []})
    monkeypatch.setattr(pipeline, "check_carousel_semantics", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("qc exploded")))
    monkeypatch.setattr(pipeline.designer, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("designer must not run")))
    monkeypatch.setattr(config, "OUTPUT_DIR", root / "output")

    result = pipeline.run("test topic", fresh=False, ctx=ctx, include_design=True)
    assert result["semantic_qc"]["ok"] is False
    assert "qc exploded" in result["semantic_qc"]["errors"][0]
    with factory() as session:
        assert session.get(Run, ctx.run_id).status == "qc_failed"
        assert session.scalar(select(Design).where(Design.run_id == ctx.run_id)) is None
        assert session.scalar(select(Event).where(Event.run_id == ctx.run_id, Event.name == "semantic_qc_failed"))
    ctx.close()
    engine.dispose()


def test_planner_receives_enterprise_products_and_goals(monkeypatch) -> None:
    captured = {}

    class FakeLLM:
        def chat(self, **kwargs):
            captured["prompt"] = kwargs["messages"][1]["content"]
            from types import SimpleNamespace
            # normalization will still be run, so force an invalid JSON path after capturing prompt.
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="not json"))])

    brand = {
        "company": "Enterprise", "industry": "IT", "description": "Digital operations",
        "products_services": [{"name": "Managed AI"}], "business_goals": ["Lead generation"],
        "target_audience": {"primary_segment": "CTO"}, "audience": "CTO",
        "content_pillars": ["AI"], "rules": [], "available_poses": [],
    }
    from src.carousel.agents import planner as planner_agent
    result = planner_agent.run("AI operations", {"sources": []}, brand, client=FakeLLM(), history=[])
    assert result["ok"] is False
    assert "Managed AI" in captured["prompt"]
    assert "Lead generation" in captured["prompt"]
