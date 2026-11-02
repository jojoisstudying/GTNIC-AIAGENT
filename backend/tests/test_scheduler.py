from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core import autonomy
from src.core.analytics_ingest import generate_real_insights
from src.core.db import (Base, ContentStrategyItem, EnterpriseProfile, PostAnalytics, ensure_schema)
from src.core.scheduler import acquire_leader, parse_due, run_once, sync_and_automate

NOW = datetime(2026, 11, 3, 3, 0, tzinfo=timezone.utc)  # = 10:00 WIB


def _factory():
    engine = create_engine("sqlite://", future=True)
    ensure_schema(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _add(f, **kw):
    base = dict(plan_date="2026-11-03", topic="t", format="carousel", content_pillar="Tips Praktis",
                objective="Edukasi", scheduled_slot="09:00 WIB", status="scheduled", run_id="r1",
                approved_by="api_user")
    base.update(kw)
    with f() as s:
        it = ContentStrategyItem(**base)
        s.add(it); s.commit()
        return it.id


def _profile(f, wf):
    import json
    with f() as s:
        s.add(EnterpriseProfile(company_name="X", industry="Y", description="Z",
                                approval_workflow_json=json.dumps(wf)))
        s.commit()


def test_parse_due_wib_to_utc():
    assert parse_due("2026-11-03", "09:00 WIB") == datetime(2026, 11, 3, 2, 0, tzinfo=timezone.utc)
    assert parse_due("2026-11-03", "xx") is None and parse_due("salah", "09:00 WIB") is None


def test_only_due_human_approved_items_published():
    f = _factory()
    due = _add(f, run_id="r_due")
    _add(f, run_id="r_future", plan_date="2026-12-01")
    _add(f, run_id="r_approved", status="approved")
    _add(f, run_id="r_unapproved", approved_by=None)
    called = []
    res = run_once(f, called.append, now=NOW)
    assert called == ["r_due"] and res == [{"item_id": due, "run_id": "r_due", "ok": True}]


def test_transient_failure_retries_with_backoff_then_gives_up():
    f = _factory()
    iid = _add(f)

    def boom(_):
        raise RuntimeError("connection timeout")

    r = run_once(f, boom, now=NOW, max_attempts=2)[0]
    assert r["status"] == "scheduled" and r["attempts"] == 1
    assert run_once(f, boom, now=NOW) == []                       # masih dalam backoff
    r = run_once(f, boom, now=NOW + timedelta(hours=1), max_attempts=2)[0]
    assert r["status"] == "publication_failed"
    with f() as s:
        assert s.get(ContentStrategyItem, iid).publish_attempts == 2


def test_permanent_failure_not_retried():
    f = _factory(); _add(f)

    class E(Exception):
        status_code = 409
        detail = "QC gagal"
    def boom(_): raise E()
    assert run_once(f, boom, now=NOW)[0]["status"] == "publication_failed"


def test_autonomy_policy():
    pol = autonomy.load_policy({"autonomy_mode": "autonomous_routine", "routine_categories": ["Tips Praktis"],
                                "required_for": ["Harga"]})
    mk = lambda pillar, by=None: ContentStrategyItem(content_pillar=pillar, objective="x", approved_by=by)
    assert autonomy.may_publish(pol, mk("Tips Praktis"))
    assert not autonomy.may_publish(pol, mk("Harga")) and autonomy.may_publish(pol, mk("Harga", "api_user"))
    assert autonomy.load_policy({"default_mode": "manual_review"})["mode"] == "assisted"
    assert autonomy.load_policy("rusak{")["mode"] == "assisted"


def test_autonomous_routine_auto_approves_and_schedules():
    from src.core.db import Run
    f = _factory()
    _profile(f, {"autonomy_mode": "autonomous_routine", "routine_categories": ["Tips Praktis"]})
    with f() as s:
        s.add(Run(id="r1", status="awaiting_approval", topic="t")); s.commit()
    iid = _add(f, status="awaiting_approval", approved_by=None)
    sync_and_automate(f)
    with f() as s:
        it = s.get(ContentStrategyItem, iid)
        assert it.status == "scheduled" and it.approved_by == "autonomy_policy"


def test_assisted_mode_never_self_approves():
    from src.core.db import Run
    f = _factory()
    with f() as s:
        s.add(Run(id="r1", status="awaiting_approval", topic="t")); s.commit()
    iid = _add(f, status="producing", approved_by=None)
    sync_and_automate(f)
    with f() as s:
        assert s.get(ContentStrategyItem, iid).status == "awaiting_approval"


def test_single_leader_lock():
    f = _factory()
    assert acquire_leader(f, owner="a", now=NOW)
    assert not acquire_leader(f, owner="b", now=NOW + timedelta(seconds=10))
    assert acquire_leader(f, owner="b", now=NOW + timedelta(seconds=500))


def test_real_insights_need_enough_data():
    f = _factory()
    with f() as s:
        assert generate_real_insights(s) == 0
        for i in range(6):
            s.add(PostAnalytics(format="carousel" if i % 2 else "video", content_pillar="p", topic="t",
                                reach=1000 + i * 100, source="instagram_graph_api", is_simulated=False,
                                ingestion_status="complete"))
        s.commit()
        assert generate_real_insights(s) == 1
        assert generate_real_insights(s) == 0  # tidak duplikat


def test_strategy_prefers_real_insight():
    import json
    from src.core.db import AnalyticsInsight
    from src.core.strategy import generate_7day_strategy
    f = _factory()
    with f() as s:
        for title, sim in (("real", False), ("demo", True)):  # demo = id lebih baru
            s.add(AnalyticsInsight(title=title, observation="o", recommended_action="a",
                                   data_points_json=json.dumps({"is_simulated": sim})))
        s.commit()
        items = generate_7day_strategy(s, use_llm=False)
        assert any("real" in (i.rationale or "") for i in items)
        assert not any("'demo'" in (i.rationale or "") for i in items)
