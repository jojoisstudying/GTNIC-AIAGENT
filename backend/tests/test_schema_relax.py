from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateTable

from src.core.db import Base, PostAnalytics, ensure_schema


def test_legacy_not_null_metric_columns_become_nullable():
    engine = create_engine("sqlite://", future=True, poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    ddl = str(CreateTable(PostAnalytics.__table__).compile(dialect=engine.dialect))
    assert "reach INTEGER" in ddl
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE post_analytics"))
        conn.execute(text(ddl.replace("reach INTEGER", "reach INTEGER NOT NULL", 1)))
    before = {c["name"]: c["nullable"] for c in inspect(engine).get_columns("post_analytics")}
    assert before["reach"] is False

    ensure_schema(engine)

    after = {c["name"]: c["nullable"] for c in inspect(engine).get_columns("post_analytics")}
    assert after["reach"] is True
    assert not inspect(engine).has_table("post_analytics__old")
