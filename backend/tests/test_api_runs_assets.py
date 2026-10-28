"""Tests: GET /api/v1/runs (riwayat) dan GET /api/v1/assets?status= (filter + counts)."""
import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src import api, config
from src.core.context import create_run_context
from src.core.db import Base, Design, Run
from src.carousel.tools import asset_library

BRAND = {"company": "Test Brand"}


@pytest.fixture()
def env(tmp_path: Path, monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    out_dir = tmp_path / "output"
    out_dir.mkdir()
    monkeypatch.setattr(config, "OUTPUT_DIR", out_dir)
    monkeypatch.setattr(api, "SessionLocal", factory)
    # asset_library memakai sqlite sendiri (data/app.db) -> arahkan ke file sementara
    monkeypatch.setattr(asset_library, "DB", tmp_path / "assets.db")
    return factory, tmp_path


def _new_run(factory, topic: str, status: str) -> str:
    ctx = create_run_context(topic, BRAND, session_factory=factory)
    run_id = ctx.run_id
    ctx.close()
    with factory() as s:
        s.get(Run, run_id).status = status
        s.commit()
    return run_id


def _asset(tmp_path: Path, name: str, status: str) -> int:
    f = tmp_path / name
    f.write_bytes(b"x")
    return asset_library.add_asset(str(f), ["senyum"], name, status=status)


def test_assets_filter_pending_alias_and_counts(env):
    _, tmp_path = env
    _asset(tmp_path, "a.png", "pending_review")
    _asset(tmp_path, "b.png", "approved")
    _asset(tmp_path, "c.png", "rejected")

    res = api.list_system_assets(status="pending")
    assert res["total"] == 1
    assert res["assets"][0]["status"] == "pending_review"
    # counts tidak terpengaruh filter
    assert res["counts"]["pending_review"] == 1
    assert res["counts"]["approved"] == 1
    assert res["counts"]["rejected"] == 1
    assert res["counts"]["all"] == 3

    assert api.list_system_assets(status=None)["total"] == 3
    assert api.list_system_assets(status="all")["total"] == 3
    assert api.list_system_assets(status="approved")["total"] == 1


def test_assets_invalid_status_is_400(env):
    with pytest.raises(HTTPException) as exc:
        api.list_system_assets(status="bogus")
    assert exc.value.status_code == 400


def test_list_runs_filter_status_and_pending_count(env):
    factory, tmp_path = env
    still_pending = _asset(tmp_path, "p1.png", "pending_review")
    already_approved = _asset(tmp_path, "p2.png", "approved")

    waiting = _new_run(factory, "carousel menunggu", "awaiting_approval")
    done = _new_run(factory, "carousel selesai", "ok")

    design = {"ok": True, "slides": [], "pending_review": [
        {"id": still_pending, "pose": "senyum"},
        {"id": already_approved, "pose": "menunjuk"},  # snapshot usang: sudah di-approve
    ]}
    with factory() as s:
        s.add(Design(run_id=waiting, version=1, ok=True, result_json=json.dumps(design)))
        s.commit()

    res = api.list_runs(limit=30, offset=0, status="awaiting_approval")
    assert res["total"] == 1
    item = res["runs"][0]
    assert item["run_id"] == waiting
    assert item["format"] == "carousel"
    assert item["pending_review_count"] == 1  # hanya yang benar-benar masih pending

    all_runs = api.list_runs(limit=30, offset=0, status=None)
    assert {r["run_id"] for r in all_runs["runs"]} == {waiting, done}


def test_list_runs_marks_video_format_and_url(env):
    factory, tmp_path = env
    run_id = _new_run(factory, "video uji", "ok")
    mp4 = config.OUTPUT_DIR / "reels" / f"reels_{run_id}.mp4"
    mp4.parent.mkdir(parents=True)
    mp4.write_bytes(b"\x00" * 10)
    with factory() as s:
        s.add(Design(run_id=run_id, version=1, ok=True, result_json=json.dumps(
            {"type": "video", "ok": True, "video_path": str(mp4)})))
        s.commit()

    item = api.list_runs(limit=10, offset=0, status=None)["runs"][0]
    assert item["format"] == "video"
    assert item["video_url"] == f"/static/output/reels/reels_{run_id}.mp4"
    assert item["pending_review_count"] == 0


def test_list_runs_limit_is_clamped(env):
    factory, _ = env
    for i in range(3):
        _new_run(factory, f"run {i}", "ok")
    res = api.list_runs(limit=0, offset=0, status=None)  # limit<1 -> 1
    assert len(res["runs"]) == 1
    assert res["total"] == 3