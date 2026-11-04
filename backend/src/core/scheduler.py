"""Scheduler persisten: sinkron status produksi, auto-approve/schedule sesuai kebijakan autonomi,
publikasi item jatuh tempo (retry+backoff), dan ingestion analytics berkala.

- Hanya satu proses yang aktif: lock leader di tabel ``scheduler_locks`` (aman untuk banyak worker).
- Aktifkan dengan ``SCHEDULER_ENABLED=true``.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from src.core import autonomy, notify  # noqa: F401  (notify: registrasi listener)
from src.core.db import Campaign, ContentStrategyItem, EnterpriseProfile, Publication, Run, SchedulerLock

log = logging.getLogger("gtnic.scheduler")

_TZ_OFFSETS = {"WIB": 7, "WITA": 8, "WIT": 9, "UTC": 0}
BACKOFF_SECONDS = [120, 300, 900, 3600]
LOCK_NAME = "main"
OWNER = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"


def parse_due(plan_date: str, slot: str) -> Optional[datetime]:
    """``2026-11-03`` + ``09:00 WIB`` -> datetime UTC. None jika tidak valid."""
    m = re.match(r"^\s*(\d{1,2}):(\d{2})\s*([A-Za-z]+)?\s*$", slot or "")
    if not m:
        return None
    try:
        day = datetime.strptime(plan_date, "%Y-%m-%d")
    except (TypeError, ValueError):
        return None
    hour, minute = int(m.group(1)), int(m.group(2))
    if hour > 23 or minute > 59:
        return None
    offset = _TZ_OFFSETS.get((m.group(3) or "WIB").upper(), 7)
    return (day.replace(hour=hour, minute=minute) - timedelta(hours=offset)).replace(tzinfo=timezone.utc)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def is_transient(exc: Exception) -> bool:
    code = getattr(exc, "status_code", None)
    if code is not None:
        return code in (408, 425, 429) or code >= 500
    text = f"{type(exc).__name__} {exc}".lower()
    return any(k in text for k in ("timeout", "timed out", "connection", "rate limit", "429", "temporar",
                                   "502", "503", "504"))


def acquire_leader(session_factory, ttl_seconds: int = 120, owner: str = OWNER,
                   now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(timezone.utc)
    expires = now + timedelta(seconds=ttl_seconds)
    with session_factory() as s:
        res = s.execute(update(SchedulerLock).where(
            SchedulerLock.name == LOCK_NAME,
            (SchedulerLock.owner == owner) | (SchedulerLock.expires_at < now),
        ).values(owner=owner, expires_at=expires))
        s.commit()
        if res.rowcount:
            return True
        try:
            s.add(SchedulerLock(name=LOCK_NAME, owner=owner, expires_at=expires))
            s.commit()
            return True
        except IntegrityError:
            s.rollback()
            return False


def _policy(session) -> dict:
    prof = session.scalars(select(EnterpriseProfile).order_by(EnterpriseProfile.id.desc())).first()
    return autonomy.load_policy(prof.approval_workflow_json if prof else None)


def sync_and_automate(session_factory) -> dict:
    """Sinkron status hasil produksi, lalu terapkan kebijakan autonomi (auto-approve / auto-schedule)."""
    stats = {"synced": 0, "auto_approved": 0, "auto_scheduled": 0}
    with session_factory() as s:
        policy = _policy(s)
        for it in s.scalars(select(ContentStrategyItem).where(
                ContentStrategyItem.status.in_(["producing", "running", "awaiting_approval", "approved"]),
                ContentStrategyItem.run_id.is_not(None))).all():
            run = s.get(Run, it.run_id)
            run_status = run.status if run else None
            if it.status in {"producing", "running"}:
                if run_status in {"awaiting_approval", "ok"}:
                    it.status = "awaiting_approval"; stats["synced"] += 1
                elif run_status in {"failed", "qc_failed", "generation_failed"}:
                    it.status = "generation_failed"; stats["synced"] += 1
            if it.status == "awaiting_approval" and run_status in {"awaiting_approval", "ok"} \
                    and autonomy.may_auto_approve(policy, it):
                it.status, it.approved_by = "approved", "autonomy_policy"; stats["auto_approved"] += 1
            if it.status == "approved" and it.approved_by and autonomy.may_auto_schedule(policy, it) \
                    and run_status in {"awaiting_approval", "ok"}:
                it.status = "scheduled"; stats["auto_scheduled"] += 1
            it.updated_at = datetime.now(timezone.utc)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        for c in s.scalars(select(Campaign).where(Campaign.status == "active", Campaign.end_date < today)).all():
            c.status = "completed"; c.updated_at = datetime.now(timezone.utc); stats["campaigns_completed"] = stats.get("campaigns_completed", 0) + 1
        s.commit()
    return stats


def run_once(session_factory, publish_fn: Callable[[str], object], now: Optional[datetime] = None,
             max_attempts: int = 4) -> list[dict]:
    """Publikasikan item jatuh tempo. Mengembalikan ringkasan per item."""
    now = now or datetime.now(timezone.utc)
    results: list[dict] = []
    due = []
    with session_factory() as s:
        policy = _policy(s)
        for it in s.scalars(select(ContentStrategyItem).where(
                ContentStrategyItem.status == "scheduled", ContentStrategyItem.run_id.is_not(None))).all():
            when = parse_due(it.plan_date, it.scheduled_slot)
            nxt = _aware(it.next_attempt_at)
            if when is None or when > now or (nxt and nxt > now):
                continue
            if not autonomy.may_publish(policy, it):
                log.info("Item %s ditahan: butuh persetujuan manusia (mode=%s).", it.id, policy["mode"])
                continue
            due.append((it.id, it.run_id))

    for item_id, run_id in due:
        try:
            publish_fn(run_id)
            results.append({"item_id": item_id, "run_id": run_id, "ok": True})
        except Exception as exc:
            detail = str(getattr(exc, "detail", None) or exc)
            log.warning("Publikasi terjadwal item %s gagal: %s", item_id, detail)
            with session_factory() as s:
                it = s.get(ContentStrategyItem, item_id)
                pubs = [p.status for p in s.scalars(select(Publication).where(Publication.run_id == run_id)).all()]
                it.publish_attempts = (it.publish_attempts or 0) + 1
                it.last_error = detail[:500]
                it.updated_at = datetime.now(timezone.utc)
                if "published" in pubs:
                    it.status = "published"
                elif "intent" in pubs:  # status tak pasti: jangan retry otomatis (cegah duplikat)
                    it.status = "publication_failed"
                    it.approval_notes = "Scheduler: status publikasi tidak pasti (intent); rekonsiliasi manual."
                elif is_transient(exc) and it.publish_attempts < max_attempts:
                    delay = BACKOFF_SECONDS[min(it.publish_attempts - 1, len(BACKOFF_SECONDS) - 1)]
                    it.status = "scheduled"
                    it.next_attempt_at = now + timedelta(seconds=delay)
                else:
                    it.status = "publication_failed"
                    it.approval_notes = f"Scheduler: {detail}"[:500]
                s.commit()
                results.append({"item_id": item_id, "run_id": run_id, "ok": False, "error": detail,
                                "status": it.status, "attempts": it.publish_attempts})
    return results


def autopilot_once(session_factory, produce_fn: Callable[[int], object], strategy_fn: Callable[[], object] | None = None,
                   research_fn: Callable[[], object] | None = None, now: Optional[datetime] = None,
                   lead_hours: int = 48, research_every_hours: int = 24, max_concurrent: int = 1,
                   stale_minutes: int = 45) -> dict:
    """Pekerjaan otonom (tanpa browser): riset harian, strategi mingguan, produksi item yang mendekati jadwal.

    Aman terhadap restart karena semua keputusan diambil dari state database, bukan memori proses.
    Produksi hanya untuk item berstatus 'approved' (manusia ATAU kebijakan autonomi) -> gate approval tetap utuh.
    """
    from src.core.db import Approval, ResearchSnapshot
    now = now or datetime.now(timezone.utc)
    stats = {"researched": 0, "strategy_generated": 0, "auto_approved": 0, "produced": 0, "errors": 0,
             "stale_runs": 0, "recovered_runs": 0}
    today = now.strftime("%Y-%m-%d")
    # Run 'running' yang terlalu lama = prosesnya mati (restart server/timeout): tandai gagal agar tidak
    # menggantung selamanya dan tidak memblokir kuota produksi.
    with session_factory() as s:
        cutoff = now - timedelta(minutes=stale_minutes)
        for r in s.scalars(select(Run).where(Run.status == "running")).all():
            started = _aware(r.started_at)
            if started and started < cutoff:
                from src.core.db import Design
                d = s.scalars(select(Design).where(Design.run_id == r.id).order_by(Design.version.desc())).first()
                if d is not None and d.ok:
                    # Output sudah jadi; thread mati sebelum status ditulis -> pulihkan, jangan dianggap gagal.
                    r.status, r.error = "awaiting_approval", None
                    stats["recovered_runs"] += 1
                else:
                    r.status, r.error = "failed", "Proses terhenti (server restart atau melewati batas waktu)."
                    stats["stale_runs"] += 1
        s.commit()
    with session_factory() as s:
        last_ok = s.scalars(select(ResearchSnapshot).where(ResearchSnapshot.ok.is_(True))
                            .order_by(ResearchSnapshot.id.desc())).first()
        last_at = _aware(last_ok.created_at) if last_ok else None
        need_research = last_at is None or (now - last_at) >= timedelta(hours=research_every_hours)
        open_future = s.scalars(select(ContentStrategyItem).where(
            ContentStrategyItem.status.in_(["draft", "awaiting_approval", "approved", "scheduled", "producing"]),
            ContentStrategyItem.plan_date >= today)).first()
    if research_fn and need_research:
        try:
            research_fn(); stats["researched"] = 1
        except Exception:
            stats["errors"] += 1; log.exception("Autopilot: riset harian gagal")
    if strategy_fn and not open_future:
        try:
            strategy_fn(); stats["strategy_generated"] = 1
        except Exception:
            stats["errors"] += 1; log.exception("Autopilot: strategi mingguan gagal")
    to_produce: list[int] = []
    with session_factory() as s:
        policy = _policy(s)
        for it in s.scalars(select(ContentStrategyItem).where(
                ContentStrategyItem.status.in_(["draft", "awaiting_approval"]),
                ContentStrategyItem.run_id.is_(None))).all():
            if autonomy.may_auto_approve(policy, it):
                it.status, it.approved_by = "approved", "autonomy_policy"
                s.add(Approval(entity_type="strategy_item", entity_id=str(it.id), decision="auto_approved",
                               actor="autonomy_policy", actor_type="policy",
                               notes=f"mode={policy['mode']}; kategori rutin"))
                stats["auto_approved"] += 1
        s.flush()
        active = 0
        for it in s.scalars(select(ContentStrategyItem).where(
                ContentStrategyItem.status.in_(["producing", "running"]), ContentStrategyItem.run_id.is_not(None))).all():
            run = s.get(Run, it.run_id)
            if run and run.status == "running":
                active += 1
        slots = max(0, max_concurrent - active)  # batasi pipeline paralel (rate limit LLM + CPU Playwright/ffmpeg)
        due_items = []
        for it in s.scalars(select(ContentStrategyItem).where(
                ContentStrategyItem.status == "approved", ContentStrategyItem.run_id.is_(None))).all():
            due = parse_due(it.plan_date, it.scheduled_slot)
            if due is None or due - now <= timedelta(hours=lead_hours):
                due_items.append((due or now, it.id))
        to_produce = [i for _, i in sorted(due_items)[:slots]]
        s.commit()
    for item_id in to_produce:
        try:
            produce_fn(item_id); stats["produced"] += 1
        except Exception:
            stats["errors"] += 1; log.exception("Autopilot: produksi item %s gagal", item_id)
    return stats


async def scheduler_loop(session_factory, publish_fn, interval_seconds: int = 60,
                         ingest_interval_seconds: int = 21600, ingest_fn: Optional[Callable] = None,
                         autopilot_fn: Optional[Callable] = None) -> None:
    log.info("Scheduler dimulai (interval %ss, owner %s)", interval_seconds, OWNER)
    last_ingest: Optional[datetime] = None
    while True:
        try:
            if await asyncio.to_thread(acquire_leader, session_factory, max(120, interval_seconds * 3)):
                await asyncio.to_thread(sync_and_automate, session_factory)
                if autopilot_fn:
                    await asyncio.to_thread(autopilot_fn)
                await asyncio.to_thread(run_once, session_factory, publish_fn)
                now = datetime.now(timezone.utc)
                if ingest_fn and (last_ingest is None or (now - last_ingest).total_seconds() >= ingest_interval_seconds):
                    last_ingest = now
                    await asyncio.to_thread(ingest_fn)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Scheduler error; dicoba lagi pada putaran berikutnya")
        await asyncio.sleep(interval_seconds)
