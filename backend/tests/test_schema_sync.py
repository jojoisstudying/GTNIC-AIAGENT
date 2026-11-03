from sqlalchemy import create_engine, inspect, text

from src.core.db import ensure_schema


def test_old_database_gets_missing_columns_and_stays_queryable():
    engine = create_engine("sqlite://", future=True)
    with engine.begin() as c:  # tabel lama: hanya sebagian kolom
        c.execute(text("CREATE TABLE post_analytics (id INTEGER PRIMARY KEY, topic TEXT)"))
        c.execute(text("INSERT INTO post_analytics (id, topic) VALUES (1, 'lama')"))
        c.execute(text("CREATE TABLE analytics_insights (id INTEGER PRIMARY KEY, title TEXT)"))
        c.execute(text("INSERT INTO analytics_insights (id, title) VALUES (1, 'lama')"))
    ensure_schema(engine)
    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns("post_analytics")}
    assert {"reach", "permalink", "ingestion_status", "is_simulated", "data_timestamp"} <= cols
    with engine.begin() as c:
        assert c.execute(text("SELECT topic FROM post_analytics WHERE id=1")).scalar() == "lama"
        assert c.execute(text("SELECT created_at FROM analytics_insights WHERE id=1")).scalar() is not None
    ensure_schema(engine)  # idempotent


def test_missing_new_tables_are_created():
    engine = create_engine("sqlite://", future=True)
    ensure_schema(engine)
    names = set(inspect(engine).get_table_names())
    assert {"notifications", "audit_log", "campaigns", "scheduler_locks", "content_strategy_items"} <= names
