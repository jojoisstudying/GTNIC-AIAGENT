"""Strategy-generation contract tests with mocked LLM and isolated storage."""
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.db import Base, ResearchSnapshot, Run
from src.core import strategy


@pytest.fixture
def strategy_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'strategy.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        profile = strategy.get_or_create_enterprise_profile(session)
        profile.products_services_json = json.dumps([{"name": "Private test product"}])
        profile.business_goals_json = json.dumps(["Private test goal"])
        profile.target_audience_json = json.dumps({"primary_segment": "Private test audience"})
        session.add(Run(id="strategy-run", topic="test", status="ok"))
        session.add(ResearchSnapshot(run_id="strategy-run", data_json=json.dumps({
            "sources": [{"title": "Evidence title", "url": "https://example.test/source"}]
        }), warnings_json="[]", ok=True))
        session.commit()
        yield session
    engine.dispose()


def test_strategy_llm_receives_enterprise_and_research_context(strategy_session, monkeypatch):
    captured = {}
    items = [{
        "offset_days": day, "topic": f"Topic {day}", "format": "carousel",
        "pillar": "Pillar", "objective": "Education", "target_segment": "Audience",
        "slot": "09:00 WIB", "rationale": "Evidence based",
    } for day in range(1, 8)]

    class FakeLLM:
        def chat(self, **kwargs):
            captured["prompt"] = kwargs["messages"][1]["content"]
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({"items": items})))])

    monkeypatch.setattr("src.core.llm.LLMClient", FakeLLM)
    results = strategy.generate_7day_strategy(strategy_session, use_llm=True)
    assert len(results) == 7
    assert "Private test product" in captured["prompt"]
    assert "Private test goal" in captured["prompt"]
    assert "Evidence title" in captured["prompt"]
    assert all("strategy_source=llm" in item.rationale for item in results)
    assert all("analytics_evidence=" in item.rationale for item in results)


def test_strategy_malformed_llm_response_uses_labeled_valid_fallback(strategy_session, monkeypatch):
    class FakeLLM:
        def chat(self, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"items":[]}'))])

    monkeypatch.setattr("src.core.llm.LLMClient", FakeLLM)
    results = strategy.generate_7day_strategy(strategy_session, use_llm=True)
    assert len(results) == 7
    assert all(item.topic and item.rationale for item in results)
    assert all("strategy_source=deterministic_fallback" in item.rationale for item in results)


def test_missing_llm_credentials_use_valid_fallback(strategy_session, monkeypatch):
    class FakeLLM:
        def chat(self, **kwargs):
            raise RuntimeError("credentials missing")

    monkeypatch.setattr("src.core.llm.LLMClient", FakeLLM)
    results = strategy.generate_7day_strategy(strategy_session, use_llm=True)
    assert len(results) == 7
    assert all(item.status == "draft" for item in results)
    assert all("strategy_source=deterministic_fallback" in item.rationale for item in results)
