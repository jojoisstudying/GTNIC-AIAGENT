import json
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.core.notify  # noqa: F401
from src.core.campaigns import breakdown, campaign_rows, evaluate, plan_items, primary_metric
from src.core.db import Campaign, ContentStrategyItem, PostAnalytics, ensure_schema
from src.core.scheduler import sync_and_automate


def _f():
    e = create_engine("sqlite://", future=True)
    ensure_schema(e)
    return sessionmaker(bind=e, expire_on_commit=False)


def _camp(s, **kw):
    c = Campaign(name="Peluncuran X", objective=kw.pop("objective", "Awareness"), start_date="2026-11-03",
                 end_date="2026-11-09", message="Pesan", performance_targets_json=json.dumps(kw.pop("t", {})), **kw)
    s.add(c); s.commit()
    return c


def test_plan_items_spread_over_period_and_linked():
    f = _f()
    with f() as s:
        c = _camp(s)
        items = plan_items(s, c, 5); s.commit()
        dates = [i.plan_date for i in items]
        assert dates[0] == "2026-11-03" and dates[-1] == "2026-11-09" and dates == sorted(dates)
        assert all(i.campaign_id == c.id and i.status == "draft" for i in items)
        assert items[0].topic.startswith("Peluncuran X:")


def _post(s, item_id, reach, likes=0, saves=0, **kw):
    s.add(PostAnalytics(strategy_item_id=item_id, format=kw.get("format", "carousel"), content_pillar="p", topic="t",
                        reach=reach, likes=likes, saves=saves, comments=0, shares=0, source="x", is_simulated=False,
                        ingestion_status="complete", data_timestamp=datetime(2026, 11, 4, tzinfo=timezone.utc)))


def test_evaluation_depends_on_objective_and_sample():
    f = _f()
    with f() as s:
        c = _camp(s, t={"reach": 1000})
        items = plan_items(s, c, 3); s.commit()
        for i, it in enumerate(items[:2]):
            _post(s, it.id, 500)
        s.commit()
        assert evaluate(c, campaign_rows(s, c.id))["status"] == "insufficient_data"  # n=2 < 3
        _post(s, items[2].id, 500); s.commit()
        ev = evaluate(c, campaign_rows(s, c.id))
        assert ev["primary_metric"] == "reach" and ev["value"] == 1500 and ev["status"] == "achieved"
        assert primary_metric("Lead generation") == "profile_visits" and primary_metric("Edukasi") == "engagement_rate"


def test_breakdown_does_not_treat_missing_as_zero():
    f = _f()
    with f() as s:
        s.add(PostAnalytics(format="video", content_pillar="a", topic="t", reach=None, source="x",
                            ingestion_status="pending"))
        _post(s, None, 200, likes=20)
        s.commit()
        b = breakdown(s.query(PostAnalytics).all())
        assert b["by_pillar"]["a"]["posts_without_reach_data"] == 1
        assert b["by_format"]["video"]["avg_reach"] is None


def test_campaign_auto_completes_after_end_date_and_notifies():
    from sqlalchemy import select
    from src.core.db import Notification
    f = _f()
    with f() as s:
        c = _camp(s); c.end_date = "2020-01-01"; s.commit()
    sync_and_automate(f)
    with f() as s:
        assert s.get(Campaign, 1).status == "completed"
        assert [n.kind for n in s.scalars(select(Notification)).all()] == ["campaign_completed"]


def test_strategy_follows_active_campaign_and_research_candidate():
    from datetime import timedelta
    from types import SimpleNamespace as NS
    from src.core.strategy import _apply_research_and_campaigns, generate_7day_strategy
    now = datetime.now()
    camp = NS(id=7, name="Peluncuran X", objective="Awareness", target_audience="UKM", message="Pesan",
              start_date=(now - timedelta(days=1)).strftime("%Y-%m-%d"), end_date=(now + timedelta(days=30)).strftime("%Y-%m-%d"))
    tpl = [{"offset_days": d, "topic": f"t{d}", "format": "carousel", "pillar": "p", "objective": "o",
            "target_segment": "x", "slot": "09:00 WIB", "rationale": "r"} for d in range(1, 8)]
    cand = [{"topic": "Topik Riset", "source_urls": ["https://x"], "recommended_format": "video",
             "relevance_score": 0.9, "relevance_reason": "cocok", "suggested_angle": "a", "risk_notes": "global"}]
    out = _apply_research_and_campaigns(tpl, False, cand, [camp], now)
    by = {t["offset_days"]: t for t in out}
    assert [d for d, t in by.items() if t.get("campaign_id") == 7] == [2, 4, 6]
    assert by[3]["topic"] == "Topik Riset" and by[3]["format"] == "video" and "Risiko: global" in by[3]["rationale"]
    # kandidat tanpa sumber tidak dipakai
    cand[0]["source_urls"] = []
    assert _apply_research_and_campaigns(tpl, False, cand, [], now)[2]["topic"] == "t3"
    # integrasi DB: item kalender tersimpan dengan campaign_id
    f = _f()
    with f() as s:
        c = Campaign(name="Aktif", objective="Awareness", start_date=camp.start_date, end_date=camp.end_date, message="m")
        s.add(c); s.commit()
        items = generate_7day_strategy(s, use_llm=False)
        assert sorted(i.campaign_id for i in items if i.campaign_id) == [c.id] * 3
