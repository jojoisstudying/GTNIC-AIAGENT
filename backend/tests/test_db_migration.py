"""Tests for schema creation and lossless migration of old asset catalogs."""
from pathlib import Path
import sqlite3

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from src.core import db


def _alembic_config(database_path: Path) -> Config:
    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    return cfg


def test_upgrade_legacy_assets_preserves_rows_and_adds_pipeline_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "data" / "app.db"
    database_path.parent.mkdir()
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "CREATE TABLE assets (id INTEGER PRIMARY KEY, path TEXT UNIQUE, tags TEXT, description TEXT)"
        )
        connection.execute(
            "INSERT INTO assets (id, path, tags, description) VALUES (7, ?, ?, ?)",
            ("data/assets/manual.png", "senyum", "manual approved asset"),
        )

    command.upgrade(_alembic_config(database_path), "head")

    engine = create_engine(f"sqlite:///{database_path}")
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT id, path, tags, description, status FROM assets WHERE id = 7")
        ).one()
    assert tuple(row) == (7, "data/assets/manual.png", "senyum", "manual approved asset", "approved")
    assert {"runs", "research_snapshots", "plans", "designs", "events", "publications",
            "credentials_status"}.issubset(set(inspect(engine).get_table_names()))
    asset_columns = {column["name"] for column in inspect(engine).get_columns("assets")}
    assert {"run_id", "sha256", "kind", "cache_key", "created_at"}.issubset(asset_columns)
    engine.dispose()


def test_sqlalchemy_engine_uses_sqlite_memory() -> None:
    engine = db.make_engine("sqlite:///:memory:")
    try:
        assert inspect(engine).get_table_names() == []
    finally:
        engine.dispose()
