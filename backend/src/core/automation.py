"""Pusat Otomatisasi: pengaturan, ringkasan, dan daftar kerja otomatisasi marketing.

Modul ini adalah satu sumber kebenaran untuk:
- konfigurasi otomatisasi (aktif/nonaktif, jam, platform, frekuensi, jenis konten,
  wajib-persetujuan) yang bisa diubah operator dari UI, bukan hanya lewat .env;
- ringkasan angka (diproses / menunggu persetujuan / terjadwal / berhasil / gagal);
- daftar konten yang menunggu persetujuan, publikasi terjadwal, dan riwayat aktivitas;
- Pause / Resume / Stop dengan efek nyata (status persisted, dibaca scheduler).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src import config
from src.core.db import (AutomationEvent, AutomationSettings, ContentStrategyItem, Publication, utc_now)

log = logging.getLogger("gtnic.automation")

STATE_RUNNING = "running"
STATE_PAUSED = "paused"
STATE_STOPPED = "stopped"
STATES = (STATE_RUNNING, STATE_PAUSED, STATE_STOPPED)

DEFAULT_DAYS = [1, 2, 3, 4, 5, 6, 7]          # 1=Senin .. 7=Minggu (isoweekday)
DEFAULT_SLOTS = ["09:00", "19:00"]
DEFAULT_FORMATS = ["carousel"]
PLATFORM_LABELS = {"instagram": "Instagram", "facebook": "Facebook"}
FACEBOOK_AVAILABLE = False
PUBLISHING_MODES = ("autopilot", "review")


def _loads(raw, fallback):
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
        return value if value is not None else fallback
    except (TypeError, ValueError):
        return fallback


def _env_flag(name: str, default: bool = False) -> bool:
    raw = (config.opt(name, "") or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def get_settings(session: Session, *, create: bool = True) -> AutomationSettings | None:
    """Ambil (atau buat) baris pengaturan otomatisasi."""
    row = session.get(AutomationSettings, 1)
    if row is not None or not create:
        return row
    # Default mengikuti konfigurasi env yang sudah ada agar perilaku lama tidak berubah.
    enabled = _env_flag("SCHEDULER_ENABLED") and _env_flag("AUTOPILOT_ENABLED", True)
    row = AutomationSettings(
        id=1,
        enabled=enabled,
        state=STATE_RUNNING if enabled else STATE_PAUSED,
        platforms_json=json.dumps(["instagram"]),
        posting_days_json=json.dumps(DEFAULT_DAYS),
        slots_json=json.dumps(DEFAULT_SLOTS),
        timezone=config.opt("AUTOMATION_TIMEZONE", "Asia/Jakarta") or "Asia/Jakarta",
        frequency_per_week=int(config.opt("AUTOPILOT_FREQUENCY_PER_WEEK", "5") or 5),
        content_formats_json=json.dumps(DEFAULT_FORMATS),
        content_pillars_json="[]",
        publishing_mode="autopilot",
        require_approval=False,
        auto_generate=_env_flag("AUTOPILOT_ENABLED", True),
        lead_hours=int(config.opt("AUTOPILOT_LEAD_HOURS", "24") or 24),
        updated_at=utc_now(),
    )
    session.add(row)
    session.commit()
    return row


def _ensure(session: Session) -> AutomationSettings:
    """Baris pengaturan yang dijamin ada (dipakai internal)."""
    row = get_settings(session, create=True)
    if row is None:  # pragma: no cover - hanya bila commit gagal
        raise RuntimeError("Pengaturan otomatisasi tidak bisa dibuat")
    return row


def serialize_settings(row: AutomationSettings) -> dict:
    platforms = [p for p in _loads(row.platforms_json, ["instagram"]) if p in PLATFORM_LABELS]
    return {
        "enabled": bool(row.enabled),
        "state": row.state,
        "is_running": row.enabled and row.state == STATE_RUNNING,
        "platforms": platforms or ["instagram"],
        "available_platforms": [
            {"key": "instagram", "label": "Instagram", "available": True},
            {"key": "facebook", "label": "Facebook", "available": FACEBOOK_AVAILABLE,
             "note": "Publikasi Facebook Page belum diimplementasikan; pilihan disimpan untuk persiapan."},
        ],
        "posting_days": _loads(row.posting_days_json, DEFAULT_DAYS),
        "slots": _loads(row.slots_json, DEFAULT_SLOTS),
        "timezone": row.timezone,
        "frequency_per_week": row.frequency_per_week,
        "content_formats": _loads(row.content_formats_json, DEFAULT_FORMATS),
        "content_pillars": _loads(row.content_pillars_json, []),
        "publishing_mode": getattr(row, "publishing_mode", "autopilot") or "autopilot",
        "require_approval": bool(row.require_approval),
        "auto_generate": bool(row.auto_generate),
        "lead_hours": row.lead_hours,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "updated_by": row.updated_by,
        "scheduler_process_enabled": _env_flag("SCHEDULER_ENABLED"),
    }


def update_settings(session: Session, payload: dict, *, actor: str = "api_user") -> AutomationSettings:
    """Perbarui pengaturan. Validasi ketat supaya scheduler tidak menerima nilai aneh."""
    row = _ensure(session)
    changed: dict = {}

    if "enabled" in payload:
        enabled = bool(payload["enabled"])
        changed["enabled"] = [row.enabled, enabled]
        row.enabled = enabled
        # Toggle "Aktifkan otomatisasi" harus punya efek nyata: ON = berjalan, OFF = dijeda.
        row.state = STATE_RUNNING if enabled else STATE_PAUSED

    if "state" in payload:
        state = str(payload["state"]).strip().lower()
        if state not in STATES:
            raise ValueError(f"state harus salah satu dari {', '.join(STATES)}")
        changed["state"] = [row.state, state]
        row.state = state
        if state == STATE_STOPPED:
            row.enabled = False
        elif state == STATE_RUNNING:
            row.enabled = True

    if "platforms" in payload:
        platforms = [str(p).strip().lower() for p in (payload["platforms"] or [])]
        invalid = [p for p in platforms if p not in PLATFORM_LABELS]
        if invalid:
            raise ValueError(f"platform tidak dikenal: {', '.join(invalid)}")
        if not platforms:
            raise ValueError("Pilih minimal satu platform.")
        changed["platforms"] = [_loads(row.platforms_json, []), platforms]
        row.platforms_json = json.dumps(platforms)

    if "posting_days" in payload:
        days = sorted({int(d) for d in (payload["posting_days"] or [])})
        if not days or any(d < 1 or d > 7 for d in days):
            raise ValueError("posting_days harus berisi angka 1 (Senin) - 7 (Minggu).")
        row.posting_days_json = json.dumps(days)

    if "slots" in payload:
        slots = []
        for raw in payload["slots"] or []:
            text = str(raw).strip()
            try:
                hour, minute = text.split(":")
                hour, minute = int(hour), int(minute)
            except (ValueError, AttributeError):
                raise ValueError(f"jam '{raw}' tidak valid; gunakan format HH:MM") from None
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError(f"jam '{raw}' di luar rentang 00:00-23:59")
            slots.append(f"{hour:02d}:{minute:02d}")
        if not slots:
            raise ValueError("Isi minimal satu jam publikasi.")
        row.slots_json = json.dumps(sorted(set(slots)))

    if "frequency_per_week" in payload:
        freq = int(payload["frequency_per_week"])
        if not 1 <= freq <= 21:
            raise ValueError("frequency_per_week harus antara 1 dan 21.")
        row.frequency_per_week = freq

    if "content_formats" in payload:
        formats = [str(f).strip().lower() for f in (payload["content_formats"] or [])]
        allowed = {"carousel", "single_image", "video"}
        invalid = [f for f in formats if f not in allowed]
        if invalid:
            raise ValueError(f"jenis konten tidak dikenal: {', '.join(invalid)}")
        if not formats:
            raise ValueError("Pilih minimal satu jenis konten.")
        row.content_formats_json = json.dumps(formats)

    if "content_pillars" in payload:
        pillars = [str(p).strip() for p in (payload["content_pillars"] or []) if str(p).strip()]
        row.content_pillars_json = json.dumps(pillars[:20])

    if "publishing_mode" in payload:
        mode = str(payload["publishing_mode"]).strip().lower()
        if mode not in PUBLISHING_MODES:
            raise ValueError(f"publishing_mode harus salah satu dari: {', '.join(PUBLISHING_MODES)}")
        changed["publishing_mode"] = [getattr(row, "publishing_mode", "autopilot"), mode]
        row.publishing_mode = mode
        # Autopilot -> require_approval = False; review -> require_approval = True
        row.require_approval = False  # approval konten dihapus

    if "require_approval" in payload and "publishing_mode" not in payload:
        changed["require_approval"] = [row.require_approval, bool(payload["require_approval"])]
        row.require_approval = False
        row.publishing_mode = "autopilot"

    if "auto_generate" in payload:
        row.auto_generate = bool(payload["auto_generate"])

    if "lead_hours" in payload:
        lead = int(payload["lead_hours"])
        if not 1 <= lead <= 168:
            raise ValueError("lead_hours harus antara 1 dan 168 jam.")
        row.lead_hours = lead

    if "timezone" in payload:
        tz = str(payload["timezone"] or "").strip()
        if tz:
            row.timezone = tz[:64]

    row.updated_at = utc_now()
    row.updated_by = actor[:64]
    session.commit()

    if changed:
        log_event(session, kind="settings", action="settings_updated", status="ok",
                  message="Pengaturan otomatisasi diperbarui: " + ", ".join(sorted(changed)),
                  actor=actor, detail={"changes": changed})
    return row


def log_event(session: Session, *, kind: str, action: str, status: str = "ok", message: str = "",
              entity_type: str | None = None, entity_id: str | None = None,
              actor: str = "system", detail: dict | None = None) -> AutomationEvent:
    """Catat satu baris riwayat aktivitas otomatisasi."""
    event = AutomationEvent(kind=kind[:48], action=action[:64], status=status[:24], message=(message or "")[:1000],
                            entity_type=entity_type, entity_id=str(entity_id) if entity_id is not None else None,
                            actor=actor[:64], detail_json=json.dumps(detail or {}, ensure_ascii=False, default=str),
                            created_at=utc_now())
    session.add(event)
    session.commit()
    return event


def serialize_event(event: AutomationEvent) -> dict:
    return {
        "id": event.id,
        "kind": event.kind,
        "action": event.action,
        "status": event.status,
        "message": event.message,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "actor": event.actor,
        "detail": _loads(event.detail_json, {}),
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }


def automation_active(session: Session) -> bool:
    """Apakah otomatisasi boleh melakukan tindakan otomatis sekarang?

    Bila baris pengaturan belum ada, perilaku lama (env) dipertahankan supaya instalasi
    yang sudah berjalan tidak berubah diam-diam sebelum operator membuka Pusat Otomatisasi.
    """
    row = get_settings(session, create=False)
    if row is None:
        return _env_flag("SCHEDULER_ENABLED") or _env_flag("AUTOPILOT_ENABLED", True)
    return bool(row.enabled) and row.state == STATE_RUNNING


def next_slot_after(session: Session, now: datetime | None = None, *, exclude_occupied: bool = True) -> datetime | None:
    """Waktu UTC berikutnya yang cocok dengan jadwal (hari + jam) yang dikonfigurasi.
    Jika exclude_occupied=True, lewati slot yang sudah memiliki publikasi terjadwal/publishing.
    """
    row = _ensure(session)
    days = set(_loads(row.posting_days_json, DEFAULT_DAYS))
    slots = _loads(row.slots_json, DEFAULT_SLOTS)
    tz_offset = _tz_offset_hours(row.timezone)
    now = now or datetime.now(timezone.utc)
    local_now = now + timedelta(hours=tz_offset)

    occupied_times: set[datetime] = set()
    if exclude_occupied:
        # Kumpulkan semua scheduled_for dari publikasi aktif (scheduled, publishing, intent)
        for pub in session.scalars(select(Publication).where(
                Publication.status.in_(("scheduled", "publishing", "intent")),
                Publication.scheduled_for.is_not(None))).all():
            if pub.scheduled_for:
                aware = pub.scheduled_for if pub.scheduled_for.tzinfo else pub.scheduled_for.replace(tzinfo=timezone.utc)
                occupied_times.add(aware)

    best: datetime | None = None
    for day_offset in range(0, 15):  # Periksa hingga 2 minggu ke depan
        day = (local_now + timedelta(days=day_offset)).date()
        if day.isoweekday() not in days:
            continue
        for slot in sorted(slots):
            hour, minute = (int(x) for x in slot.split(":"))
            candidate_local = datetime(day.year, day.month, day.day, hour, minute)
            candidate = candidate_local - timedelta(hours=tz_offset)
            candidate = candidate.replace(tzinfo=timezone.utc)
            if candidate > now:
                if exclude_occupied and candidate in occupied_times:
                    continue
                if best is None or candidate < best:
                    best = candidate
                    break
        if best:
            break
    return best


def _tz_offset_hours(name: str) -> int:
    """Offset jam untuk zona yang lazim di Indonesia (default WIB)."""
    mapping = {"Asia/Jakarta": 7, "Asia/Makassar": 8, "Asia/Jayapura": 9, "UTC": 0, "WIB": 7, "WITA": 8, "WIT": 9}
    return mapping.get(name, 7)


def summary(session: Session) -> dict:
    """Ringkasan angka untuk kartu di Pusat Otomatisasi."""
    counts: dict[str, int] = {}
    for status, count in session.execute(
            select(Publication.status, func.count(Publication.id)).group_by(Publication.status)).all():
        counts[str(status)] = int(count)
    generated = session.scalar(select(func.count(ContentStrategyItem.id))) or 0
    published = counts.get("published", 0)

    processed = session.scalar(select(func.count(ContentStrategyItem.id)).where(
        ContentStrategyItem.status.not_in(("draft", "rejected")))) or 0
    pub_failed = counts.get("failed", 0)
    failed_pub_items = select(Publication.strategy_item_id).where(
        Publication.status == "failed", Publication.strategy_item_id.is_not(None))
    calendar_failed = session.scalar(select(func.count(ContentStrategyItem.id)).where(
        ContentStrategyItem.status.in_(("generation_failed", "publication_failed")),
        ContentStrategyItem.id.not_in(failed_pub_items))) or 0
    total_failed = pub_failed + calendar_failed

    return {
        "total_processed": processed,
        "awaiting_approval": counts.get("pending_approval", 0),
        "scheduled": counts.get("scheduled", 0),
        "publishing": counts.get("publishing", 0) + counts.get("intent", 0),
        "published": published,
        "failed": total_failed,
        "cancelled": counts.get("cancelled", 0),
        "calendar_items": generated,
        "queued_generation": session.scalar(select(func.count(ContentStrategyItem.id)).where(
            ContentStrategyItem.status.in_(("approved", "producing")))) or 0,
    }


def pending_approvals(session: Session, limit: int = 50) -> list[Publication]:
    return list(session.scalars(
        select(Publication).where(Publication.status == "pending_approval")
        .order_by(Publication.created_at.asc()).limit(limit)))


def scheduled_publications(session: Session, limit: int = 50) -> list[Publication]:
    return list(session.scalars(
        select(Publication).where(Publication.status.in_(("scheduled", "publishing", "intent")))
        .order_by(Publication.scheduled_for.asc().nulls_last(), Publication.created_at.asc()).limit(limit)))


def recent_events(session: Session, limit: int = 30) -> list[AutomationEvent]:
    return list(session.scalars(
        select(AutomationEvent).order_by(AutomationEvent.id.desc()).limit(max(1, min(limit, 200)))))


def pause(session: Session, *, actor: str = "api_user") -> AutomationSettings:
    row = _ensure(session)
    row.state, row.enabled = STATE_PAUSED, False
    row.updated_at, row.updated_by = utc_now(), actor[:64]
    session.commit()
    log_event(session, kind="control", action="paused", status="ok",
              message="Otomatisasi dijeda. Konten terjadwal tidak akan dipublikasikan otomatis.",
              actor=actor)
    return row


def resume(session: Session, *, actor: str = "api_user") -> AutomationSettings:
    row = _ensure(session)
    row.state, row.enabled = STATE_RUNNING, True
    row.updated_at, row.updated_by = utc_now(), actor[:64]
    session.commit()
    log_event(session, kind="control", action="resumed", status="ok",
              message="Otomatisasi dilanjutkan.", actor=actor)
    return row


def stop(session: Session, *, cancel_scheduled: bool = True, actor: str = "api_user") -> dict:
    """Hentikan otomatisasi. Item 'scheduled' dibatalkan agar tidak tayang setelah dihentikan."""
    row = _ensure(session)
    row.state, row.enabled = STATE_STOPPED, False
    row.updated_at, row.updated_by = utc_now(), actor[:64]
    cancelled = 0
    if cancel_scheduled:
        rows = session.scalars(select(Publication).where(Publication.status == "scheduled")).all()
        for pub in rows:
            pub.status = "cancelled"
            pub.error = "Otomatisasi dihentikan oleh pengguna."
            pub.updated_at = utc_now()
            cancelled += 1
        session.commit()
    else:
        session.commit()
    log_event(session, kind="control", action="stopped", status="ok",
              message=f"Otomatisasi dihentikan. {cancelled} publikasi terjadwal dibatalkan.",
              actor=actor, detail={"cancelled_scheduled": cancelled})
    return {"cancelled_scheduled": cancelled}
