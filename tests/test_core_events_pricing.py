"""Core event and pricing persistence tests."""
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from src.core.db import Base, Event
from src.core.events import EventEmitter
from src.core.pricing import calculate_llm_cost, provider_units


def test_event_is_persisted_and_printed(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'events.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    output: list[str] = []

    EventEmitter("run-test", factory, output.append).emit(
        "llm", "sample-model", step="planner", tokens_in=100, tokens_out=50,
        cost_usd=0.001, detail={"source": "unit-test"},
    )

    with factory() as session:
        event = session.scalar(select(Event).where(Event.run_id == "run-test"))
    assert event is not None
    assert event.kind == "llm"
    assert event.tokens_in == 100
    assert '"source": "unit-test"' in event.detail_json
    assert output and "planner | llm sample-model" in output[0]
    engine.dispose()


def test_pricing_calculates_cost_and_provider_units() -> None:
    rates = {
        "models": {"demo": {"input_per_million_usd": 2.0,
                              "output_per_million_usd": 4.0}},
        "providers": {"tavily": {"units_per_search": 1.0}},
    }
    assert calculate_llm_cost("demo", 1_000_000, 500_000, rates) == 4.0
    assert provider_units("tavily", 3, rates) == 3.0
