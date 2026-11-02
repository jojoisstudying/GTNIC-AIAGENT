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
            "credentials_status", "enterprise_profile_versions"}.issubset(set(inspect(engine).get_table_names()))
    asset_columns = {column["name"] for column in inspect(engine).get_columns("assets")}
    assert {"run_id", "sha256", "kind", "cache_key", "created_at"}.issubset(asset_columns)
    assert {"publication_id", "ingestion_status", "data_timestamp"}.issubset(
        {column["name"] for column in inspect(engine).get_columns("post_analytics")}
    )
    assert {"enterprise_profile_id", "enterprise_profile_version"}.issubset(
        {column["name"] for column in inspect(engine).get_columns("runs")}
    )
    assert "semantic_qc_json" in {column["name"] for column in inspect(engine).get_columns("designs")}
    engine.dispose()


def test_sqlalchemy_engine_uses_sqlite_memory() -> None:
    engine = db.make_engine("sqlite:///:memory:")
    try:
        assert inspect(engine).get_table_names() == []
    finally:
        engine.dispose()


def test_optional_image_processing_requirements_are_separate():
    root = Path(__file__).resolve().parents[1]
    core = (root / "requirements.txt").read_text(encoding="utf-8")
    optional = (root / "requirements-image-processing.txt").read_text(encoding="utf-8")
    assert "moviepy==2.2.1" in core and "Pillow==11.3.0" in core
    assert "rembg[cpu]==2.0.82" in optional and "Pillow==12.3.0" in optional
    active_requirements = [line.strip() for line in core.splitlines()
                           if line.strip() and not line.lstrip().startswith("#")]
    assert not any(line.startswith("rembg") for line in active_requirements)


