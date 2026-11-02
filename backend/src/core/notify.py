"""Notifikasi + audit log otomatis.

Listener ``before_flush`` pada Session menangkap perubahan penting di mana pun terjadi
(API, scheduler, pipeline) tanpa perlu hook manual di tiap endpoint:
status item kalender, status run (QC/generasi gagal), update profil enterprise, dan insight baru.
"""
from __future__ import annotations

import json
from contextvars import ContextVar

from sqlalchemy import event, inspect as sa_inspect
from sqlalchemy.orm import Session

from src.core.db import (AnalyticsInsight, AuditLog, Campaign, ContentStrategyItem, EnterpriseProfile,
                         Notification, Run)

current_actor: ContextVar[str] = ContextVar("current_actor", default="system")

_ITEM_NOTIFS = {
    "awaiting_approval": ("approval_requested", "info", "Persetujuan dibutuhkan"),
    "published": ("publication_success", "info", "Konten berhasil dipublikasikan"),
    "publication_failed": ("publication_failed", "error", "Publikasi gagal"),
    "generation_failed": ("generation_failed", "error", "Produksi konten gagal"),
}


def _changed(obj, attr):
    h = sa_inspect(obj).attrs[attr].history
    return (h.deleted[0] if h.deleted else None, h.added[0] if h.added else None) if h.has_changes() else None


def _on_before_flush(session: Session, _ctx, _instances) -> None:
    actor = current_actor.get()
    for obj in list(session.new):
        if isinstance(obj, AnalyticsInsight):
            try:
                real = json.loads(obj.data_points_json or "{}").get("is_simulated") is False
            except ValueError:
                real = False
            if real:
                session.add(Notification(kind="insight", title="Insight analytics baru", message=obj.title,
                                         entity_type="analytics_insight", entity_id=str(obj.id or "")))
    for obj in list(session.dirty):
        if isinstance(obj, ContentStrategyItem) and (ch := _changed(obj, "status")):
            old, new = ch
            session.add(AuditLog(actor=actor, action="item_status_changed", entity_type="content_strategy_item",
                                 entity_id=str(obj.id), detail_json=json.dumps(
                                     {"from": old, "to": new, "topic": obj.topic, "approved_by": obj.approved_by},
                                     ensure_ascii=False)))
            if new in _ITEM_NOTIFS:
                kind, sev, title = _ITEM_NOTIFS[new]
                detail = obj.last_error or obj.approval_notes or ""
                session.add(Notification(kind=kind, title=title, severity=sev,
                                         message=f"{obj.topic[:120]}" + (f" — {detail[:200]}" if sev == "error" and detail else ""),
                                         entity_type="content_strategy_item", entity_id=str(obj.id)))
        elif isinstance(obj, Campaign) and (ch := _changed(obj, "status")):
            session.add(AuditLog(actor=actor, action="campaign_status_changed", entity_type="campaign",
                                 entity_id=str(obj.id), detail_json=json.dumps({"from": ch[0], "to": ch[1]})))
            if ch[1] == "completed":
                session.add(Notification(kind="campaign_completed", title="Kampanye selesai", message=obj.name,
                                         entity_type="campaign", entity_id=str(obj.id)))
        elif isinstance(obj, Run) and (ch := _changed(obj, "status")) and ch[1] in {"qc_failed", "failed"}:
            session.add(Notification(kind="qc_failed" if ch[1] == "qc_failed" else "run_failed",
                                     title="QC gagal" if ch[1] == "qc_failed" else "Run gagal", severity="error",
                                     message=(obj.error or obj.topic or "")[:300], entity_type="run", entity_id=obj.id))
        elif isinstance(obj, EnterpriseProfile) and session.is_modified(obj, include_collections=False):
            session.add(AuditLog(actor=actor, action="enterprise_profile_updated",
                                 entity_type="enterprise_profile", entity_id=str(obj.id)))


if not event.contains(Session, "before_flush", _on_before_flush):
    event.listen(Session, "before_flush", _on_before_flush)
