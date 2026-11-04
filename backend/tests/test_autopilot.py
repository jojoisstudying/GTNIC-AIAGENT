from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.core import scheduler
from src.core.db import Approval, ContentStrategyItem, Run, ensure_schema

NOW = datetime(2026, 11, 5, 3, 0, tzinfo=timezone.utc)


def _factory():
    engine = create_engine("sqlite://", future=True, poolclass=StaticPool, connect_args={"check_same_thread": False})
    ensure_schema(engine)
    return sessionmaker(engine, expire_on_commit=False)


def _item(status, plan_date="2026-11-05", slot="09:00 WIB", fmt="carousel", run_id=None):
    return ContentStrategyItem(plan_date=plan_date, topic="t", format=fmt, content_pillar="Tips Praktis",
                               objective="Edukasi", scheduled_slot=slot, status=status, run_id=run_id)


def test_autopilot_produces_only_approved_due_items():
    sf = _factory()
    with sf() as s:
        s.add_all([_item("approved"), _item("draft"), _item("approved", plan_date="2026-12-30")])
        s.commit()
    produced = []
    stats = scheduler.autopilot_once(sf, produced.append, now=NOW, lead_hours=48)
    assert stats["produced"] == 1 and len(produced) == 1
    with sf() as s:
        ids = {i.status for i in s.scalars(select(ContentStrategyItem)).all()}
    assert "draft" in ids  # draft tidak pernah diproduksi tanpa persetujuan


def test_autopilot_generates_strategy_only_when_no_open_future_items():
    sf = _factory()
    calls = []
    scheduler.autopilot_once(sf, lambda i: None, strategy_fn=lambda: calls.append(1), now=NOW)
    assert calls == [1]
    with sf() as s:
        s.add(_item("scheduled", plan_date="2026-11-06"))
        s.commit()
    scheduler.autopilot_once(sf, lambda i: None, strategy_fn=lambda: calls.append(1), now=NOW)
    assert calls == [1]  # masih ada item terbuka -> tidak generate ulang


def test_autopilot_does_not_auto_approve_in_default_assisted_mode():
    sf = _factory()
    with sf() as s:
        s.add(_item("draft"))
        s.commit()
    stats = scheduler.autopilot_once(sf, lambda i: None, now=NOW)
    assert stats["auto_approved"] == 0
    with sf() as s:
        assert s.scalars(select(Approval)).first() is None


def test_autopilot_error_in_one_job_does_not_stop_others():
    sf = _factory()
    with sf() as s:
        s.add(_item("approved"))
        s.commit()
    def boom():
        raise RuntimeError("x")
    produced = []
    stats = scheduler.autopilot_once(sf, produced.append, research_fn=boom, now=NOW)
    assert stats["errors"] == 1 and stats["produced"] == 1  # riset gagal, produksi tetap jalan
    sf2 = _factory()
    stats2 = scheduler.autopilot_once(sf2, produced.append, strategy_fn=boom, now=NOW)
    assert stats2["errors"] == 1


def test_autopilot_respects_max_concurrent_and_picks_earliest_first():
    sf = _factory()
    with sf() as s:
        s.add_all([_item("approved", slot="18:30 WIB"), _item("approved", slot="09:00 WIB")])
        s.commit()
        early_id = s.scalars(select(ContentStrategyItem).where(ContentStrategyItem.scheduled_slot == "09:00 WIB")).one().id
    produced = []
    scheduler.autopilot_once(sf, produced.append, now=NOW, lead_hours=48, max_concurrent=1)
    assert produced == [early_id]


def test_autopilot_blocks_new_production_while_another_run_is_active():
    sf = _factory()
    with sf() as s:
        s.add(Run(id="r" * 32, topic="x", status="running", started_at=NOW - timedelta(minutes=5)))
        s.add(_item("producing", run_id="r" * 32))
        s.add(_item("approved", slot="10:00 WIB"))
        s.commit()
    produced = []
    scheduler.autopilot_once(sf, produced.append, now=NOW, max_concurrent=1)
    assert produced == []


def test_autopilot_marks_stale_running_runs_failed_and_frees_the_slot():
    sf = _factory()
    with sf() as s:
        s.add(Run(id="s" * 32, topic="x", status="running", started_at=NOW - timedelta(hours=3)))
        s.add(_item("producing", run_id="s" * 32, plan_date="2026-11-05"))
        s.add(_item("approved", slot="10:00 WIB", plan_date="2026-11-05"))
        s.commit()
    produced = []
    stats = scheduler.autopilot_once(sf, produced.append, now=NOW, max_concurrent=1, stale_minutes=45)
    assert stats["stale_runs"] == 1 and len(produced) == 1
    with sf() as s:
        assert s.get(Run, "s" * 32).status == "failed"
