"""Operations Center: notifikasi, audit log, dan status operasional."""
import json
import os
from collections import Counter
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, func, select, update

from src import config
from src.core import auth
from src.core.db import (AuditLog, ContentStrategyItem, Notification, PostAnalytics, Publication,
                         SchedulerLock, SessionLocal)

router = APIRouter(prefix="/api/v1")


def _aware(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _item(i):
    return {"id": i.id, "topic": i.topic, "format": i.format, "plan_date": i.plan_date,
            "scheduled_slot": i.scheduled_slot, "status": i.status, "approved_by": i.approved_by,
            "publish_attempts": i.publish_attempts or 0, "last_error": i.last_error,
            "next_attempt_at": _aware(i.next_attempt_at).isoformat() if i.next_attempt_at else None}


@router.get("/notifications", dependencies=[Depends(auth.verify_api_key)])
def list_notifications(unread_only: bool = False, limit: int = 50):
    with SessionLocal() as s:
        q = select(Notification).order_by(desc(Notification.id)).limit(max(1, min(limit, 200)))
        if unread_only:
            q = q.where(Notification.is_read.is_(False))
        rows = s.scalars(q).all()
        unread = s.scalar(select(func.count()).select_from(Notification).where(Notification.is_read.is_(False)))
        return {"unread": unread, "items": [
            {"id": n.id, "kind": n.kind, "title": n.title, "message": n.message, "severity": n.severity,
             "entity_type": n.entity_type, "entity_id": n.entity_id, "is_read": n.is_read,
             "created_at": _aware(n.created_at).isoformat()} for n in rows]}


@router.post("/notifications/read-all", dependencies=[Depends(auth.verify_api_key)])
def read_all_notifications():
    with SessionLocal() as s:
        res = s.execute(update(Notification).where(Notification.is_read.is_(False)).values(is_read=True))
        s.commit()
        return {"marked": res.rowcount}


@router.post("/notifications/{notif_id}/read", dependencies=[Depends(auth.verify_api_key)])
def read_notification(notif_id: int):
    with SessionLocal() as s:
        n = s.get(Notification, notif_id)
        if not n:
            raise HTTPException(status_code=404, detail="Notifikasi tidak ditemukan")
        n.is_read = True
        s.commit()
        return {"status": "ok"}


@router.get("/audit-log", dependencies=[Depends(auth.verify_api_key)])
def audit_log(limit: int = 100, action: str | None = None):
    with SessionLocal() as s:
        q = select(AuditLog).order_by(desc(AuditLog.id)).limit(max(1, min(limit, 500)))
        if action:
            q = q.where(AuditLog.action == action)
        return {"items": [{"id": a.id, "actor": a.actor, "action": a.action, "entity_type": a.entity_type,
                           "entity_id": a.entity_id, "detail": json.loads(a.detail_json or "{}"),
                           "created_at": _aware(a.created_at).isoformat()} for a in s.scalars(q).all()]}


@router.get("/ops/status", dependencies=[Depends(auth.verify_api_key)])
def ops_status():
    now = datetime.now(timezone.utc)
    with SessionLocal() as s:
        lock = s.get(SchedulerLock, "main")
        exp = _aware(lock.expires_at) if lock else None
        items = s.scalars(select(ContentStrategyItem)).all()
        key = lambda i: (i.plan_date, i.scheduled_slot)
        pubs = s.scalars(select(Publication).order_by(desc(Publication.id)).limit(10)).all()
        last_ingest = s.scalar(select(func.max(PostAnalytics.data_timestamp)).where(PostAnalytics.is_simulated.is_(False)))
        return {
            "scheduler": {
                "enabled": config.opt("SCHEDULER_ENABLED", "false").lower() == "true",
                "active": bool(exp and exp > now), "leader": lock.owner if lock else None,
                "lease_expires_at": exp.isoformat() if exp else None,
            },
            "calendar_by_status": dict(Counter(i.status for i in items)),
            "upcoming_publications": [_item(i) for i in sorted((i for i in items if i.status == "scheduled"), key=key)[:10]],
            "pending_approvals": [_item(i) for i in sorted((i for i in items if i.status == "awaiting_approval"), key=key)],
            "failed_workflows": [_item(i) for i in items if i.status in {"publication_failed", "generation_failed"}],
            "retrying": [_item(i) for i in items if i.status == "scheduled" and (i.publish_attempts or 0) > 0],
            "recent_publications": [{"run_id": p.run_id, "status": p.status, "media_id": p.media_id,
                                     "permalink": p.permalink, "error": p.error} for p in pubs],
            "analytics_ingestion": {
                "last_real_metrics_at": _aware(last_ingest).isoformat() if last_ingest else None,
                "pending_records": s.scalar(select(func.count()).select_from(PostAnalytics).where(PostAnalytics.ingestion_status == "pending")),
                "instagram_configured": bool(config.opt("IG_USER_ID")),
            },
            "unread_notifications": s.scalar(select(func.count()).select_from(Notification).where(Notification.is_read.is_(False))),
            "environment": os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "development")),
        }
