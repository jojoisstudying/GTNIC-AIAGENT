import json

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from src.core.db import AnalyticsInsight, AuditLog, ContentStrategyItem, Notification, ensure_schema
import src.core.notify  # noqa: F401
from src.core.notify import current_actor


def _factory():
    engine = create_engine("sqlite://", future=True)
    ensure_schema(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _item(s, status="draft"):
    it = ContentStrategyItem(plan_date="2026-11-03", topic="Topik uji", format="carousel", content_pillar="p",
                             objective="o", scheduled_slot="09:00 WIB", status=status)
    s.add(it); s.commit()
    return it


def test_status_change_creates_audit_and_notification():
    f = _factory()
    with f() as s:
        it = _item(s, "publishing")
        current_actor.set("api_user")
        it.status, it.last_error = "publication_failed", "Token IG kedaluwarsa"
        s.commit()
        current_actor.set("system")
        a = s.scalars(select(AuditLog)).all()
        n = s.scalars(select(Notification)).all()
        assert a[0].action == "item_status_changed" and a[0].actor == "api_user"
        assert json.loads(a[0].detail_json)["to"] == "publication_failed"
        assert n[0].kind == "publication_failed" and n[0].severity == "error" and "Token IG" in n[0].message


def test_approval_requested_and_unchanged_status_silent():
    f = _factory()
    with f() as s:
        it = _item(s, "producing")
        it.status = "awaiting_approval"; s.commit()
        assert [x.kind for x in s.scalars(select(Notification)).all()] == ["approval_requested"]
        it.approval_notes = "catatan"; s.commit()  # status tidak berubah
        assert len(s.scalars(select(Notification)).all()) == 1


def test_only_real_insight_notifies():
    f = _factory()
    with f() as s:
        for sim in (True, False):
            s.add(AnalyticsInsight(title=f"i{sim}", observation="o", recommended_action="a",
                                   data_points_json=json.dumps({"is_simulated": sim})))
        s.commit()
        assert [n.message for n in s.scalars(select(Notification)).all()] == ["iFalse"]
