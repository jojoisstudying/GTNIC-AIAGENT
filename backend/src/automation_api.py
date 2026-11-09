"""API Pusat Otomatisasi + alur persetujuan publikasi + analytics per konten.

Endpoint yang disediakan (semua tombol di UI terhubung ke sini):

Publikasi & persetujuan
  GET    /api/v1/publications                 daftar publikasi (filter status/run/platform)
  GET    /api/v1/publications/{pub_id}        detail satu publikasi
  POST   /api/v1/runs/{run_id}/publication    siapkan draf publikasi (preview + status menunggu)
  PATCH  /api/v1/publications/{pub_id}        edit caption/hashtag/gambar/jadwal
  POST   /api/v1/publications/{pub_id}/approve     Setujui & Publikasikan (idempoten)
  POST   /api/v1/publications/{pub_id}/publish     publikasi draf yang sudah disetujui tanpa jadwal
  POST   /api/v1/publications/{pub_id}/cancel      Batalkan Publikasi
  GET    /api/v1/runs/{run_id}/publication         status publikasi sebuah run

Pusat Otomatisasi
  GET    /api/v1/automation                pengaturan + ringkasan + daftar kerja + aktivitas
  PUT    /api/v1/automation                perbarui pengaturan
  POST   /api/v1/automation/pause|resume|stop
  GET    /api/v1/automation/activity       riwayat aktivitas (pagination sederhana)

Analytics per konten
  GET    /api/v1/analytics/publications           daftar konten yang bisa dipilih
  GET    /api/v1/analytics/publications/{id}      metrik + riwayat + perbandingan

Pembatalan generasi
  POST   /api/v1/runs/{run_id}/cancel

Diagnostik
  GET    /api/v1/integrations/instagram/status
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select

from src import config
from src.core import auth, automation, publication_service as ps
from src.core.db import (Approval, ContentStrategyItem, Event, PostAnalytics, PostAnalyticsSnapshot,
                         Publication, Run, SessionLocal, utc_now)
from src.core.publication_service import PublicationError

log = logging.getLogger("gtnic.automation_api")
router = APIRouter(prefix="/api/v1")


def _publisher():
    """Impor publisher dengan session factory yang sama dengan API (penting untuk tes & multi-DB)."""
    from src.agents import publisher
    if getattr(publisher, "SessionLocal", None) is not SessionLocal:
        publisher.SessionLocal = SessionLocal
    return publisher


def _actor(request: Request | None) -> str:
    if request is None:
        return "api_user"
    raw = request.headers.get("X-User-Name") or "api_user"
    cleaned = "".join(ch for ch in raw if ch.isalnum() or ch in " ._-@")[:64]
    return cleaned or "api_user"


def _parse_dt(value: str | None) -> datetime | None:
    """Terima ISO-8601 dengan/tanpa zona; None bila kosong."""
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Format tanggal/jam tidak valid: {value}") from None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _calendar_format(fmt: str | None) -> str:
    return {"video": "reel", "single_image": "image"}.get((fmt or "").lower(), "carousel")


def _strategy_item_for_run(session, run_id: str | None) -> ContentStrategyItem | None:
    if not run_id:
        return None
    return session.scalars(select(ContentStrategyItem).where(
        ContentStrategyItem.run_id == run_id)).first()


def _assert_run_qc_passed(session, run_id: str | None) -> None:
    """Pastikan run terkait benar-benar valid dan lulus QC sebelum disiapkan / disetujui / dipublikasikan."""
    if not run_id:
        return
    run = session.get(Run, run_id)
    if not run:
        return
    if run.status in ("failed", "qc_failed", "generation_failed"):
        raise HTTPException(status_code=400, detail=f"Konten dari run '{run_id}' gagal QC ({run.status}: {run.error or 'tidak lulus QC'}). Tidak dapat dipersiapkan atau disetujui.")
    if run.status == "cancelled":
        raise HTTPException(status_code=409, detail=f"Run '{run_id}' telah dibatalkan.")


def _publication_payload(session, pub: Publication) -> dict:
    data = ps.serialize(pub)
    item = session.get(ContentStrategyItem, pub.strategy_item_id) if pub.strategy_item_id else None
    if item is None:
        item = _strategy_item_for_run(session, pub.run_id)
    data["topic"] = item.topic if item else None
    data["content_pillar"] = item.content_pillar if item else None
    data["format"] = item.format if item else ("video" if pub.media_type == "reel" else "carousel")
    run = session.get(Run, pub.run_id) if pub.run_id else None
    data["run_status"] = run.status if run else None
    if not data["topic"] and run:
        data["topic"] = run.topic
    return data


# ---------------------------------------------------------------------------
# Persiapan draf publikasi dari sebuah run
# ---------------------------------------------------------------------------

class PreparePublicationRequest(BaseModel):
    caption: Optional[str] = Field(None, description="Caption final dari editor; kosong = pakai draf AI")
    hashtags: Optional[list[str]] = Field(None, description="Hashtag tanpa/tanpa tanda #")
    scheduled_for: Optional[str] = Field(None, description="ISO-8601 waktu publikasi; kosong = langsung")
    platform: str = Field("instagram")
    image_urls: Optional[list[str]] = Field(None, description="URL/path media terpilih (maks 10)")
    media_type: Optional[str] = Field(None, description="carousel | image | reel")


@router.post("/runs/{run_id}/publication", dependencies=[Depends(auth.verify_api_key)])
def prepare_publication(run_id: str, req: PreparePublicationRequest, request: Request):
    """Siapkan draf publikasi untuk sebuah run: status Menunggu Persetujuan (atau Dijadwalkan).

    Tidak memanggil API Meta sama sekali — hanya menyiapkan baris publikasi + preview.
    """
    with SessionLocal() as session:
        run = session.get(Run, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run tidak ditemukan")
        _assert_run_qc_passed(session, run_id)
        if run.status == "cancelled":
            raise HTTPException(status_code=409, detail="Run ini dibatalkan; buat konten baru.")
        item = _strategy_item_for_run(session, run_id)
        media_urls = req.image_urls
        media_type = req.media_type

        if not media_urls:
            media_urls, detected = _media_from_run(session, run)
            media_type = media_type or detected
        if not media_urls:
            raise HTTPException(status_code=400,
                                detail="Run ini belum punya media siap publikasi (selesai dirender / QC lolos).")

        existing = ps.get_for_run(session, run_id, req.platform)
        if existing and existing.status in (ps.PUBLISHED, ps.INTENT, ps.PUBLISHING):
            return {"ok": True, "already_exists": True, "publication": _publication_payload(session, existing)}

        require_approval = _require_approval(session)
        scheduled_for = _parse_dt(req.scheduled_for)
        if not scheduled_for and not require_approval:
            # Mode autopilot: bila tidak diberikan jadwal eksplisit, jadwalkan ke target slot kalender/otomatis
            dummy_pub = Publication(strategy_item_id=item.id if item else None, run_id=run_id)
            scheduled_for = _schedule_target(session, dummy_pub)
        plan = {"caption": req.caption, "hashtags": req.hashtags}
        if req.caption is None:
            plan = _plan_from_run(session, run)

        if existing:
            pub = ps.update_draft(session, existing, caption=plan.get("caption"),
                                  hashtags=plan.get("hashtags"), image_urls=media_urls,
                                  scheduled_for=scheduled_for, media_type=media_type) if (
                existing.status == ps.PENDING_APPROVAL or existing.status == ps.SCHEDULED
            ) else existing
        else:
            pub = ps.ensure_pending(session, run_id=run_id, plan=plan, media_type=media_type or "carousel",
                                    image_urls=media_urls, strategy_item_id=item.id if item else None,
                                    platform=req.platform, scheduled_for=scheduled_for,
                                    require_approval=require_approval, actor=_actor(request))
        if item and scheduled_for and require_approval:
            item.status = "scheduled" if item.status not in {"published", "publishing"} else item.status
            session.commit()
        return {"ok": True, "requires_approval": pub.status == ps.PENDING_APPROVAL,
                "publication": _publication_payload(session, pub)}


def _require_approval(session) -> bool:
    row = automation.get_settings(session, create=False)
    return False  # approval hanya untuk ide; publikasi tidak pernah menunggu approval


def _plan_from_run(session, run: Run) -> dict:
    from src.core.db import Plan
    plan_row = session.scalars(select(Plan).where(Plan.run_id == run.id)
                               .order_by(desc(Plan.version))).first()
    if plan_row and plan_row.plan_json:
        try:
            return json.loads(plan_row.plan_json) or {}
        except ValueError:
            pass
    return {"caption": run.topic, "hashtags": []}


def _media_from_run(session, run: Run) -> tuple[list[str], str]:
    """Path/URL media siap publikasi dari desain terakhir (slide carousel atau video Reels)."""
    from src.core.db import Design
    design_row = session.scalars(select(Design).where(Design.run_id == run.id)
                                 .order_by(desc(Design.version))).first()
    if not design_row or not design_row.result_json:
        return [], ""
    try:
        data = json.loads(design_row.result_json)
    except ValueError:
        return [], ""
    if data.get("type") == "video":
        path = data.get("video_path")
        return ([path], "reel") if path and data.get("ok") else ([], "")
    if not design_row.ok:
        return [], ""
    slides = [s.get("path") for s in (data.get("slides") or []) if s.get("path")]
    return slides, ("carousel" if len(slides) > 1 else "image")


@router.get("/runs/{run_id}/publication", dependencies=[Depends(auth.verify_api_key)])
def get_run_publication(run_id: str):
    """Status publikasi terkini untuk satu run (dipakai preview konten & polling frontend)."""
    with SessionLocal() as session:
        pub = ps.get_for_run(session, run_id)
        if not pub:
            return {"run_id": run_id, "publication": None, "status": "not_prepared"}
        return {"run_id": run_id, "publication": _publication_payload(session, pub)}


class PublicationEditRequest(BaseModel):
    caption: Optional[str] = None
    hashtags: Optional[list[str]] = None
    scheduled_for: Optional[str] = None
    clear_schedule: bool = False
    image_urls: Optional[list[str]] = None
    media_type: Optional[str] = None


@router.patch("/publications/{pub_id}", dependencies=[Depends(auth.verify_api_key)])
def edit_publication(pub_id: int, req: PublicationEditRequest):
    """Edit caption/hashtag/gambar/jadwal sebelum publikasi."""
    with SessionLocal() as session:
        pub = session.get(Publication, pub_id)
        if not pub:
            raise HTTPException(status_code=404, detail="Publikasi tidak ditemukan")
        try:
            ps.update_draft(session, pub, caption=req.caption, hashtags=req.hashtags,
                            scheduled_for=_parse_dt(req.scheduled_for),
                            clear_schedule=req.clear_schedule, image_urls=req.image_urls,
                            media_type=req.media_type)
        except PublicationError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from None
        return {"ok": True, "publication": _publication_payload(session, pub)}


class ApproveRequest(BaseModel):
    publish_now: bool = Field(True, description="False = setujui lalu biarkan terjadwal")
    scheduled_for: Optional[str] = None


@router.post("/publications/{pub_id}/approve", dependencies=[Depends(auth.verify_api_key)])
def approve_publication(pub_id: int, request: Request, req: Optional[ApproveRequest] = None):
    """Setujui & Publikasikan.

    - Idempoten: yang sudah disetujui tidak meminta persetujuan lagi.
    - Bila ``scheduled_for`` ada di masa depan, konten hanya dijadwalkan (tidak tayang sekarang).
    - Bila tidak dijadwalkan, backend langsung mempublikasikan ke Instagram.
    """
    publisher = _publisher()

    req = req or ApproveRequest()
    actor = _actor(request)
    with SessionLocal() as session:
        pub = session.get(Publication, pub_id)
        if not pub:
            raise HTTPException(status_code=404, detail="Publikasi tidak ditemukan")
        _assert_run_qc_passed(session, pub.run_id)
        if pub.status == ps.PUBLISHED:
            return {"ok": True, "already_published": True,
                    "publication": _publication_payload(session, pub)}
        publish_now = bool(req.publish_now)
        if req.scheduled_for:
            try:
                ps.update_draft(session, pub, scheduled_for=_parse_dt(req.scheduled_for))
                # Bila scheduled_for ada dan di masa depan, jangan publish_now
                due_at = ps._aware(pub.scheduled_for)
                if due_at and due_at > ps.utc_now():
                    publish_now = False
            except PublicationError as exc:
                raise HTTPException(status_code=exc.status_code, detail=str(exc)) from None
        elif not publish_now and pub.scheduled_for is None:
            # Sama seperti approve-all: tentukan target jadwal dari kalender / slot otomatis
            target = _schedule_target(session, pub)
            if target is not None:
                pub.scheduled_for = target
                session.commit()
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Jadwal publikasi tidak dapat ditentukan. Harap tentukan scheduled_for atau konfigurasi hari dan jam posting di Pengaturan Otomatisasi."
                )
        try:
            ps.approve(session, pub, actor=actor, publish_now=publish_now)
        except PublicationError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from None
        session.refresh(pub)
        automation.log_event(session, kind="approval", action="approved", status="ok",
                             message=f"Konten '{_topic_label(session, pub)}' disetujui",
                             entity_type="publication", entity_id=str(pub.id), actor=actor,
                             detail={"scheduled_for": pub.scheduled_for.isoformat() if pub.scheduled_for else None})
        if pub.status == ps.SCHEDULED:
            return {"ok": True, "status": pub.status, "requires_approval": False,
                    "publication": _publication_payload(session, pub),
                    "message": "Konten disetujui dan dijadwalkan. Akan dipublikasikan otomatis sesuai jadwal."}
        if not req.publish_now:
            # publish_now=False: persetujuan dicatat, tetapi TIDAK ada panggilan ke API Meta.
            return {"ok": True, "status": pub.status, "requires_approval": False,
                    "publication": _publication_payload(session, pub),
                    "message": "Konten disetujui. Publikasikan lewat tombol Publikasikan bila sudah siap."}

    # Publikasi sekarang (di luar sesi baca: upload + API Meta memakan waktu).
    try:
        result = publisher.execute_publication(pub_id)
    except PublicationError as exc:
        with SessionLocal() as session:
            pub = session.get(Publication, pub_id)
            return {"ok": False, "status": pub.status if pub else ps.FAILED,
                    "error": str(exc), "publication": _publication_payload(session, pub) if pub else None}
    with SessionLocal() as session:
        pub = session.get(Publication, pub_id)
        automation.log_event(session, kind="publication", action="published",
                             status="ok" if result.get("ok") else "error",
                             message=f"Konten '{_topic_label(session, pub)}' dipublikasikan ke Instagram",
                             entity_type="publication", entity_id=str(pub_id), actor="system",
                             detail={"media_id": result.get("media_id"), "permalink": result.get("permalink")})
        return {"ok": bool(result.get("ok")), "status": result.get("status"),
                "media_id": result.get("media_id"), "permalink": result.get("permalink"),
                "publication": _publication_payload(session, pub) if pub else None}


@router.post("/publications/{pub_id}/publish", dependencies=[Depends(auth.verify_api_key)])
def publish_now(pub_id: int):
    """Publikasikan draf yang SUDAH disetujui (mis. setelah memperbaiki error)."""
    publisher = _publisher()
    with SessionLocal() as session:
        pub = session.get(Publication, pub_id)
        if not pub:
            raise HTTPException(status_code=404, detail="Publikasi tidak ditemukan")
        _assert_run_qc_passed(session, pub.run_id)
        if pub.status == ps.PUBLISHED:
            return {"ok": True, "already_published": True, "media_id": pub.media_id,
                    "permalink": pub.permalink, "status": ps.PUBLISHED,
                    "publication": _publication_payload(session, pub)}
        if pub.approved_at is None:
            raise HTTPException(status_code=409,
                                detail="Konten belum disetujui. Gunakan tombol Setujui & Publikasikan.")
    try:
        result = publisher.execute_publication(pub_id)
    except PublicationError as exc:
        with SessionLocal() as session:
            pub = session.get(Publication, pub_id)
            return {"ok": False, "status": pub.status if pub else ps.FAILED, "error": str(exc),
                    "publication": _publication_payload(session, pub) if pub else None}
    with SessionLocal() as session:
        pub = session.get(Publication, pub_id)
        return {"ok": bool(result.get("ok")), **result,
                "publication": _publication_payload(session, pub) if pub else None}


@router.post("/publications/{pub_id}/cancel", dependencies=[Depends(auth.verify_api_key)])
def cancel_publication(pub_id: int, request: Request):
    """Batalkan publikasi yang belum tayang."""
    with SessionLocal() as session:
        pub = session.get(Publication, pub_id)
        if not pub:
            raise HTTPException(status_code=404, detail="Publikasi tidak ditemukan")
        try:
            ps.cancel(session, pub, actor=_actor(request))
        except PublicationError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from None
        automation.log_event(session, kind="publication", action="cancelled", status="ok",
                             message=f"Publikasi '{_topic_label(session, pub)}' dibatalkan",
                             entity_type="publication", entity_id=str(pub_id), actor=_actor(request))
        return {"ok": True, "publication": _publication_payload(session, pub)}


@router.get("/publications", dependencies=[Depends(auth.verify_api_key)])
def list_publications(status: Optional[str] = None, run_id: Optional[str] = None,
                      platform: Optional[str] = None, limit: int = 50):
    """Daftar publikasi dengan filter. Dipakai semua panel UI."""
    limit = max(1, min(limit, 200))
    with SessionLocal() as session:
        q = select(Publication).order_by(desc(Publication.id)).limit(limit)
        if status:
            wanted = [s.strip() for s in status.split(",") if s.strip()]
            invalid = [s for s in wanted if s not in ps.STATUSES]
            if invalid:
                raise HTTPException(status_code=400,
                                    detail=f"status tidak dikenal: {', '.join(invalid)}")
            q = q.where(Publication.status.in_(wanted))
        if run_id:
            q = q.where(Publication.run_id == run_id)
        if platform:
            q = q.where(Publication.platform == platform)
        rows = session.scalars(q).all()
        return {"total": len(rows), "items": [_publication_payload(session, p) for p in rows],
                "statuses": [{"key": s, "label": ps.STATUS_LABELS[s]} for s in ps.STATUSES]}


@router.get("/publications/{pub_id}", dependencies=[Depends(auth.verify_api_key)])
def get_publication(pub_id: int):
    with SessionLocal() as session:
        pub = session.get(Publication, pub_id)
        if not pub:
            raise HTTPException(status_code=404, detail="Publikasi tidak ditemukan")
        return _publication_payload(session, pub)


class ApproveAllRequest(BaseModel):
    publications: bool = Field(True, description="Setujui draf publikasi yang menunggu persetujuan")
    calendar: bool = Field(True, description="Setujui ide kalender yang masih draf/menunggu")
    schedule_missing: bool = Field(True, description="Beri jadwal otomatis pada publikasi yang belum punya jadwal")


def _schedule_target(session, pub: Publication) -> datetime | None:
    """Waktu tayang untuk publikasi tanpa jadwal: slot item kalender (bila masih di masa depan), lalu slot berikutnya yang kosong."""
    item = session.get(ContentStrategyItem, pub.strategy_item_id) if pub.strategy_item_id else None
    if item is None and pub.run_id:
        item = _strategy_item_for_run(session, pub.run_id)
    now = datetime.now(timezone.utc)
    if item is not None and item.plan_date and item.scheduled_slot:
        from src.core.scheduler import parse_due
        due = parse_due(item.plan_date, item.scheduled_slot)
        # Jangan gunakan slot kalender yang sudah lampau (lewat waktu)!
        if due is not None and due > now:
            # Periksa apakah slot ini sudah ditempati publikasi lain
            occupied = session.scalar(select(Publication).where(
                Publication.id != pub.id,
                Publication.status.in_((ps.SCHEDULED, ps.PUBLISHING, ps.INTENT)),
                Publication.scheduled_for == due))
            if not occupied:
                return due
    return automation.next_slot_after(session, now=now, exclude_occupied=True)


@router.post("/publications/approve-all", dependencies=[Depends(auth.verify_api_key)])
def approve_all(request: Request, req: Optional[ApproveAllRequest] = None):
    """Setujui SEMUA konten minggu ini sekaligus — tanpa memanggil API Meta sama sekali.

    - Draf publikasi -> disetujui + dijadwalkan (TIDAK tayang langsung; scheduler yang menayangkan).
    - Ide kalender (draft / awaiting_approval / generation_failed) -> ``approved`` (siap diproduksi).
    Idempoten: menjalankan ulang tidak menyetujui apa pun lagi.
    """
    req = req or ApproveAllRequest()
    actor = _actor(request)
    approved_pubs = approved_items = 0
    skipped: list[dict] = []
    errors: list[dict] = []

    with SessionLocal() as session:
        if req.publications:
            pubs = session.scalars(select(Publication).where(
                Publication.status.in_(tuple(_BATCH_PUB_STATUSES)))).all()
            for pub in pubs:
                if pub.media_id:
                    skipped.append({"kind": "publication", "ref_id": pub.id,
                                    "reason": "sudah punya media_id (sudah tayang)"})
                    continue
                try:
                    if req.schedule_missing and pub.scheduled_for is None:
                        target = _schedule_target(session, pub)
                        if target is not None:
                            pub.scheduled_for = target
                            session.commit()
                        else:
                            raise PublicationError("Jadwal publikasi tidak dapat ditentukan (jadwal kosong).", status_code=400)
                    ps.approve(session, pub, actor=actor, publish_now=False)
                    approved_pubs += 1
                except PublicationError as exc:
                    session.rollback()
                    errors.append({"kind": "publication", "ref_id": pub.id, "error": str(exc)})

        if req.calendar:
            from src.core.strategy import CALENDAR_TRANSITIONS
            items = session.scalars(select(ContentStrategyItem).where(
                ContentStrategyItem.status.in_(tuple(_BATCH_ITEM_STATUSES)))).all()
            for item in items:
                if "approved" not in CALENDAR_TRANSITIONS.get(item.status, set()):
                    skipped.append({"kind": "calendar", "ref_id": item.id,
                                    "reason": f"status '{item.status}' tidak bisa disetujui"})
                    continue
                if item.status == "generation_failed":
                    item.run_id = None  # lepaskan run gagal agar bisa diproduksi ulang
                item.status = "approved"
                item.approved_by = actor
                item.approval_notes = None
                item.updated_at = utc_now()
                session.add(Approval(entity_type="strategy_item", entity_id=str(item.id),
                                     run_id=item.run_id, decision="approved", actor=actor,
                                     actor_type="human", notes="Setujui semua (batch)"))
                approved_items += 1
            session.commit()

        automation.log_event(
            session, kind="approval", action="approved_all", status="ok",
            message=f"Setujui semua: {approved_pubs} publikasi + {approved_items} ide konten",
            actor=actor,
            detail={"publications": approved_pubs, "calendar_items": approved_items,
                    "skipped": len(skipped), "errors": len(errors)})
        payload = _automation_payload(session)

    return {"ok": True, "approved_publications": approved_pubs,
            "approved_calendar_items": approved_items,
            "skipped": skipped, "errors": errors, **payload}


def _topic_label(session, pub: Publication | None) -> str:
    if pub is None:
        return "-"
    item = session.get(ContentStrategyItem, pub.strategy_item_id) if pub.strategy_item_id else None
    if item and item.topic:
        return item.topic[:120]
    run = session.get(Run, pub.run_id) if pub.run_id else None
    return (run.topic if run else "")[:120] or f"#{pub.id}"


# ---------------------------------------------------------------------------
# Ringkasan minggu (kalender + publikasi) & status pipeline live
# ---------------------------------------------------------------------------

# Status yang dipakai UI. Nilai internal kalender/publikasi dipetakan ke satu
# kosakata agar tabel minggu mudah dibaca orang non-teknis.
WEEK_STATUS = {
    "needs_approval": ("Perlu disetujui", "warning"),
    "draft": ("Draf", "neutral"),
    "ready": ("Siap dibuat", "brand"),
    "scheduled": ("Terjadwal", "brand"),
    "publishing": ("Sedang diproses", "brand"),
    "published": ("Sudah tayang", "success"),
    "failed": ("Gagal", "danger"),
    "stuck": ("Perlu dicek", "neutral"),
    "cancelled": ("Dibatalkan", "neutral"),
    "rejected": ("Ditolak", "neutral"),
}

_PUB_STATUS_MAP = {
    ps.PENDING_APPROVAL: "needs_approval",
    ps.SCHEDULED: "scheduled",
    ps.PUBLISHING: "publishing",
    ps.INTENT: "publishing",
    ps.PUBLISHED: "published",
    ps.FAILED: "failed",
    ps.CANCELLED: "cancelled",
}

_ITEM_STATUS_MAP = {
    "draft": "draft",
    "awaiting_approval": "needs_approval",
    "approved": "ready",
    "approved_to_publish": "ready",
    "producing": "publishing",
    "scheduled": "scheduled",
    "publishing": "publishing",
    "published": "published",
    "generation_failed": "publishing",  # diproses ulang otomatis, tidak ditampilkan sebagai gagal
    "needs_check": "stuck",
    "publication_failed": "failed",
    "rejected": "rejected",
}

# Item kalender yang boleh disetujui lewat "Setujui Semua" (hanya yang draf / menunggu persetujuan ide).
_BATCH_ITEM_STATUSES = {"draft", "awaiting_approval"}
# Publikasi yang masih boleh disetujui (hanya yang menunggu persetujuan).
_BATCH_PUB_STATUSES = {ps.PENDING_APPROVAL}


def _iso(value) -> str | None:
    if value is None:
        return None
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return aware.isoformat()


def _week_row(*, kind: str, ref_id: int, topic: str, fmt: str, status_key: str, date: str | None,
              slot: str | None, when: str | None, **extra) -> dict:
    label, tone = WEEK_STATUS.get(status_key, (status_key, "neutral"))
    row = {
        "kind": kind,
        "ref_id": ref_id,
        "publication_id": extra.pop("publication_id", None),
        "item_id": extra.pop("item_id", None),
        "run_id": extra.pop("run_id", None),
        "topic": topic or "",
        "format": fmt or "carousel",
        "status": status_key,
        "status_label": label,
        "status_tone": tone,
        "date": date,
        "slot": slot,
        "when": when,
        "can_approve": extra.pop("can_approve", False),
        "can_cancel": extra.pop("can_cancel", False),
        "can_publish": extra.pop("can_publish", False),
        "permalink": extra.pop("permalink", None),
        "media_id": extra.pop("media_id", None),
        "error": extra.pop("error", None),
        "scheduled_for": extra.pop("scheduled_for", None),
        "publish_attempts": extra.pop("publish_attempts", 0),
    }
    row.update(extra)
    return row


def _slot_hm(raw: str | None) -> str | None:
    """'09:00 WIB' -> '09:00' (label zona tidak ikut ditampilkan di tabel)."""
    if not raw:
        return None
    return str(raw).strip().split()[0]


def week_overview(session, *, days: int = 7) -> list[dict]:
    """Daftar konten minggu ini: publikasi (yang sudah punya baris) + item kalender.

    Satu konten tidak tampil dua kali: item kalender dilewati bila run/item-nya sudah
    punya baris publikasi. Urut berdasarkan waktu tayang/jadwal.
    """
    pubs = session.scalars(select(Publication).order_by(Publication.id.asc())).all()
    _tz = timedelta(hours=automation._tz_offset_hours(automation._ensure(session).timezone))

    covered_runs: set[str] = set()
    covered_items: set[int] = set()
    rows: list[dict] = []

    for pub in pubs:
        if pub.run_id:
            covered_runs.add(pub.run_id)
        if pub.strategy_item_id:
            covered_items.add(pub.strategy_item_id)
        item = session.get(ContentStrategyItem, pub.strategy_item_id) if pub.strategy_item_id else None
        if item is None and pub.run_id:
            item = _strategy_item_for_run(session, pub.run_id)
            if item is not None:
                covered_items.add(item.id)
        due = _parse_dt(pub.scheduled_for.isoformat()) if pub.scheduled_for else None
        published = _parse_dt(pub.published_at.isoformat()) if pub.published_at else None
        when_dt = due or published
        when_local = (when_dt + _tz) if when_dt else None
        rows.append(_week_row(
            kind="publication",
            ref_id=pub.id,
            publication_id=pub.id,
            item_id=item.id if item else None,
            run_id=pub.run_id,
            topic=(item.topic if item and item.topic else (pub.caption or "").split("\n")[0]),
            fmt=pub.media_type or (item.format if item else "carousel"),
            status_key=_PUB_STATUS_MAP.get(pub.status, "draft"),
            date=when_local.strftime("%Y-%m-%d") if when_local else (item.plan_date if item else None),
            slot=when_local.strftime("%H:%M") if when_local else _slot_hm(item.scheduled_slot if item else None),
            when=_iso(pub.scheduled_for) or _iso(pub.published_at),
            can_approve=pub.status in _BATCH_PUB_STATUSES and not pub.media_id,
            can_retry=pub.status == ps.FAILED and not pub.media_id,
            can_cancel=pub.status in ps.CANCELLABLE,
            can_publish=pub.status in (ps.SCHEDULED, ps.FAILED) and not pub.media_id and pub.approved_at is not None,
            permalink=pub.permalink,
            media_id=pub.media_id,
            error=pub.error,
            scheduled_for=_iso(pub.scheduled_for),
            publish_attempts=pub.publish_attempts or 0,
        ))

    for item in session.scalars(select(ContentStrategyItem).order_by(ContentStrategyItem.id.asc())).all():
        if item.id in covered_items or (item.run_id and item.run_id in covered_runs):
            continue
        rows.append(_week_row(
            kind="calendar",
            ref_id=item.id,
            item_id=item.id,
            run_id=item.run_id,
            topic=item.topic,
            fmt=item.format,
            status_key=_ITEM_STATUS_MAP.get(item.status, "draft"),
            date=item.plan_date,
            slot=_slot_hm(item.scheduled_slot),
            when=None,
            can_approve=item.status in _BATCH_ITEM_STATUSES,
            can_retry=item.status == "generation_failed",
            can_cancel=False,
            can_publish=False,
            error=item.last_error,
            publish_attempts=item.publish_attempts or 0,
            content_pillar=item.content_pillar,
            approved_by=item.approved_by,
        ))

    now = datetime.now(timezone.utc) + _tz
    # Batasi kalender: mulai dari awal minggu (atau hari ini - 1 hari) hingga 7 hari ke depan
    min_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    max_date = (now + timedelta(days=days)).strftime("%Y-%m-%d")
    # Status final (tayang/gagal/batal/ditolak) tetap tampil 30 hari; hanya yang aktif dibatasi jendela minggu.
    hist_min = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    final_keys = {"published", "failed", "cancelled", "rejected"}

    def _keep(r):
        d = r.get("date")
        if not d:
            return True
        if r.get("status") in final_keys:
            return hist_min <= d <= max_date
        return min_date <= d <= max_date
    filtered_rows = [r for r in rows if _keep(r)]

    filtered_rows.sort(key=lambda r: ((r.get("date") or "9999-12-31"), (r.get("slot") or "99:99"),
                                     r.get("kind") != "publication", r.get("ref_id") or 0))
    return filtered_rows[-200:]


def live_status(session, *, limit: int = 5, stale_minutes: int = 45) -> dict:
    """Transparansi proses: run yang sedang jalan + publikasi yang sedang diproses.

    Run berstatus 'running' yang aktivitas terakhirnya lebih lama dari ``stale_minutes``
    dianggap macet (server restart/proses mati) dan TIDAK ditampilkan sebagai proses live —
    kalau ditampilkan, halaman akan berbohong soal pekerjaan yang sebenarnya sudah berhenti.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=stale_minutes)
    active = []
    stale = 0
    rows = session.scalars(
        select(Run).where(Run.status == "running").order_by(desc(Run.started_at)).limit(limit * 3)).all()
    for run in rows:
        last = session.scalars(select(Event).where(Event.run_id == run.id)
                               .order_by(desc(Event.id)).limit(1)).first()
        reference = _to_utc(last.ts if last else run.started_at)
        if reference is not None and reference < cutoff:
            stale += 1
            continue
        if len(active) >= limit:
            continue
        active.append({
            "run_id": run.id,
            "topic": run.topic,
            "status": run.status,
            "started_at": _iso(run.started_at),
            "step": (last.step if last else None) or "pipeline",
            "stage": (last.name if last else None) or "menyiapkan",
            "stage_status": (last.status if last else None) or "running",
            "last_event_at": _iso(last.ts) if last else None,
        })
    publishing = session.scalar(select(func.count(Publication.id)).where(
        Publication.status.in_((ps.PUBLISHING, ps.INTENT)))) or 0
    return {"active_runs": active, "publishing_count": int(publishing), "stale_runs": stale,
            "idle": not active and not publishing}


def _to_utc(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Pusat Otomatisasi
# ---------------------------------------------------------------------------

class AutomationUpdateRequest(BaseModel):
    enabled: Optional[bool] = None
    state: Optional[str] = None
    platforms: Optional[list[str]] = None
    posting_days: Optional[list[int]] = None
    slots: Optional[list[str]] = None
    timezone: Optional[str] = None
    frequency_per_week: Optional[int] = None
    content_formats: Optional[list[str]] = None
    content_pillars: Optional[list[str]] = None
    publishing_mode: Optional[str] = None
    require_approval: Optional[bool] = None
    auto_generate: Optional[bool] = None
    lead_hours: Optional[int] = None


def _automation_payload(session) -> dict:
    row = automation._ensure(session)
    settings = automation.serialize_settings(row)
    nxt = automation.next_slot_after(session)
    week = week_overview(session)
    return {
        "settings": settings,
        "summary": automation.summary(session),
        "next_slot": nxt.isoformat() if nxt else None,
        "week": week,
        "week_counts": {
            "total": len(week),
            "needs_approval": sum(1 for r in week if r["status"] == "needs_approval"),
            "ready": sum(1 for r in week if r["status"] == "ready"),
            "scheduled": sum(1 for r in week if r["status"] == "scheduled"),
            "publishing": sum(1 for r in week if r["status"] == "publishing"),
            "published": sum(1 for r in week if r["status"] == "published"),
            "failed": sum(1 for r in week if r["status"] == "failed"),
        },
        "live": live_status(session),
        "pending_approvals": [_publication_payload(session, p)
                              for p in automation.pending_approvals(session)],
        "scheduled": [_publication_payload(session, p)
                      for p in automation.scheduled_publications(session)],
        "activity": [automation.serialize_event(e) for e in automation.recent_events(session, 25)],
        "scheduler_process_enabled": (config.opt("SCHEDULER_ENABLED", "false").lower() == "true"),
        "server_time": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/automation", dependencies=[Depends(auth.verify_api_key)])
def get_automation_center():
    """Semua data Pusat Otomatisasi dalam satu panggilan (settings, ringkasan, antrian, aktivitas)."""
    with SessionLocal() as session:
        return _automation_payload(session)


@router.put("/automation", dependencies=[Depends(auth.verify_api_key)])
def update_automation_center(req: AutomationUpdateRequest, request: Request):
    payload = {k: v for k, v in req.model_dump().items() if v is not None}
    if not payload:
        raise HTTPException(status_code=400, detail="Tidak ada perubahan yang dikirim.")
    with SessionLocal() as session:
        try:
            automation.update_settings(session, payload, actor=_actor(request))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        return {"ok": True, **_automation_payload(session)}


def _control(action: str, request: Request | None) -> dict:
    actor = _actor(request)
    with SessionLocal() as session:
        if action == "pause":
            automation.pause(session, actor=actor)
        elif action == "resume":
            automation.resume(session, actor=actor)
        else:
            automation.stop(session, actor=actor)
        session.expire_all()
        return {"ok": True, **_automation_payload(session)}


@router.post("/automation/pause", dependencies=[Depends(auth.verify_api_key)])
def pause_automation(request: Request):
    """Pause: hentikan sementara, jadwal & antrian tetap tersimpan."""
    return _control("pause", request)


@router.post("/automation/resume", dependencies=[Depends(auth.verify_api_key)])
def resume_automation(request: Request):
    return _control("resume", request)


@router.post("/automation/stop", dependencies=[Depends(auth.verify_api_key)])
def stop_automation(request: Request):
    """Stop: matikan otomatisasi dan batalkan publikasi terjadwal yang belum tayang."""
    return _control("stop", request)


@router.get("/automation/activity", dependencies=[Depends(auth.verify_api_key)])
def automation_activity(limit: int = 50):
    with SessionLocal() as session:
        return {"items": [automation.serialize_event(e)
                          for e in automation.recent_events(session, limit)]}


# ---------------------------------------------------------------------------
# Analytics per konten
# ---------------------------------------------------------------------------

def _metric_block(row: PostAnalytics | None) -> dict:
    if row is None:
        return {"available": False}
    return {
        "available": True,
        "reach": row.reach,
        "impressions": row.impressions,
        "views": getattr(row, "views", None),
        "likes": row.likes,
        "comments": row.comments,
        "shares": row.shares,
        "saves": row.saves,
        "profile_visits": row.profile_visits,
        "total_interactions": getattr(row, "total_interactions", None),
        "engagement_rate": row.engagement_rate,
        "source": row.source,
        "ingestion_status": row.ingestion_status,
        "is_simulated": row.is_simulated,
        "collected_at": row.data_timestamp.isoformat() if row.data_timestamp else None,
    }


@router.get("/analytics/publications", dependencies=[Depends(auth.verify_api_key)])
def analytics_publications(limit: int = 50):
    """Daftar konten yang punya media_id Instagram (bisa dipilih untuk melihat performa)."""
    limit = max(1, min(limit, 200))
    with SessionLocal() as session:
        pubs = session.scalars(select(Publication).where(
            Publication.status == ps.PUBLISHED, Publication.media_id.is_not(None))
            .order_by(desc(Publication.published_at)).limit(limit)).all()
        items = []
        for pub in pubs:
            row = session.scalar(select(PostAnalytics).where(PostAnalytics.publication_id == pub.id))
            items.append({
                "publication_id": pub.id,
                "media_id": pub.media_id,
                "topic": _topic_label(session, pub),
                "format": pub.media_type or "carousel",
                "platform": pub.platform,
                "permalink": pub.permalink,
                "published_at": pub.published_at.isoformat() if pub.published_at else None,
                "metrics": _metric_block(row),
                "engagement_rate": row.engagement_rate if row else None,
                "reach": row.reach if row else None,
            })
        return {"total": len(items), "items": items}


@router.get("/analytics/publications/{pub_id}", dependencies=[Depends(auth.verify_api_key)])
def analytics_publication_detail(pub_id: int):
    """Detail performa satu konten + riwayat snapshot + perbandingan dengan konten lain."""
    with SessionLocal() as session:
        pub = session.get(Publication, pub_id)
        if not pub:
            raise HTTPException(status_code=404, detail="Konten tidak ditemukan")
        if not pub.media_id:
            raise HTTPException(status_code=409,
                                detail="Konten ini belum punya ID postingan Instagram, jadi metrik belum tersedia.")
        row = session.scalar(select(PostAnalytics).where(PostAnalytics.publication_id == pub.id))
        snapshots = session.scalars(select(PostAnalyticsSnapshot)
                                    .where(PostAnalyticsSnapshot.publication_id == pub.id)
                                    .order_by(PostAnalyticsSnapshot.collected_at.asc())).all()
        peers = session.scalars(select(PostAnalytics).where(
            PostAnalytics.publication_id != pub.id,
            PostAnalytics.is_simulated.is_(False)).order_by(desc(PostAnalytics.id)).limit(12)).all()
        return {
            "publication_id": pub.id,
            "media_id": pub.media_id,
            "topic": _topic_label(session, pub),
            "format": pub.media_type or "carousel",
            "permalink": pub.permalink,
            "published_at": pub.published_at.isoformat() if pub.published_at else None,
            "metrics": _metric_block(row),
            "available_metrics": _available_metrics(row),
            "history": [{
                "collected_at": s.collected_at.isoformat() if s.collected_at else None,
                "reach": s.reach, "views": s.views, "likes": s.likes, "comments": s.comments,
                "saves": s.saves, "shares": s.shares, "engagement_rate": s.engagement_rate,
                "metrics_available": json.loads(s.metrics_available_json or "[]"),
            } for s in snapshots],
            "comparison": [{
                "publication_id": p.publication_id, "topic": p.topic, "format": p.format,
                "reach": p.reach, "likes": p.likes, "comments": p.comments, "saves": p.saves,
                "engagement_rate": p.engagement_rate, "permalink": p.permalink,
            } for p in peers],
        }


def _available_metrics(row: PostAnalytics | None) -> dict:
    """Bedakan 'belum tersedia' (False) dari 'nol' (True + nilai 0)."""
    if row is None:
        return {}
    return {k: getattr(row, k) is not None for k in
            ("reach", "impressions", "views", "likes", "comments", "shares", "saves",
             "profile_visits", "total_interactions", "engagement_rate")}


class IngestRequest(BaseModel):
    publication_id: Optional[int] = None
    window_days: int = 30


@router.post("/analytics/publications/ingest", dependencies=[Depends(auth.verify_api_key)])
def ingest_metrics(req: Optional[IngestRequest] = None):
    """Tarik metrik Instagram (nyata) untuk satu konten atau semua konten dalam jendela waktu."""
    from src.core.analytics_ingest import fetch_instagram_metrics, ingest_all, ingest_publication

    req = req or IngestRequest()
    if not config.opt("IG_USER_ID") or not config.opt("IG_TOKEN"):
        raise HTTPException(
            status_code=409,
            detail="Instagram belum terhubung: IG_USER_ID dan IG_TOKEN wajib dikonfigurasi di backend/.env."
        )
    if req.publication_id:
        with SessionLocal() as session:
            pub = session.get(Publication, req.publication_id)
            if not pub or not pub.media_id:
                raise HTTPException(status_code=409,
                                    detail="Konten belum punya media_id Instagram; metrik belum bisa diambil.")
            try:
                metrics = ingest_publication(session, pub, fetch_instagram_metrics)
            except Exception as exc:  # noqa: BLE001 - pesan Meta diteruskan ke UI
                raise HTTPException(status_code=502, detail=f"Gagal mengambil metrik: {exc}") from None
            return {"ok": True, "publication_id": pub.id, "metrics": metrics}
    result = ingest_all(SessionLocal, window_days=max(1, min(req.window_days, 180)))
    return {"ok": True, **result}


# ---------------------------------------------------------------------------
# Pembatalan generasi + diagnostik integrasi
# ---------------------------------------------------------------------------

@router.post("/runs/{run_id}/cancel", dependencies=[Depends(auth.verify_api_key)])
def cancel_run(run_id: str, request: Request):
    """Batalkan proses pembuatan konten yang sedang berjalan.

    Backend menandai run sebagai cancelled dan menghentikan pipeline pada unit kerja
    berikutnya. Token yang sudah diproses provider tidak bisa ditarik kembali; tujuannya
    menghentikan pekerjaan lanjutan dan mencegah biaya tambahan.
    """
    from src.core import cancellation

    with SessionLocal() as session:
        run = session.get(Run, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run tidak ditemukan")
        if run.status in {"ok", "failed", "qc_failed", "awaiting_approval", "awaiting_assets", "cancelled"}:
            if run.status == "cancelled":
                return {"ok": True, "status": "cancelled", "already": True}
            return {"ok": False, "status": run.status,
                    "message": f"Run sudah selesai (status '{run.status}') sehingga tidak bisa dibatalkan."}
        cancellation.request_cancel(run_id)
        run.status = "cancelled"
        run.error = None
        run.finished_at = datetime.now(timezone.utc)
        item = _strategy_item_for_run(session, run_id)
        if item and item.status in {"producing", "running", "awaiting_approval", "approved"}:
            item.status = "draft"
            item.approval_notes = "Generasi dibatalkan pengguna"
            item.run_id = None
        automation.log_event(session, kind="generation", action="cancelled", status="ok",
                             message=f"Generasi konten '{run.topic[:120]}' dibatalkan",
                             entity_type="run", entity_id=run_id, actor=_actor(request))
        session.commit()
    return {"ok": True, "status": "cancelled", "run_id": run_id}


@router.get("/integrations/instagram/status", dependencies=[Depends(auth.verify_api_key)])
def instagram_integration_status(live: bool = True):
    """Diagnostik kesiapan publikasi Instagram (tanpa mempublikasikan apa pun)."""
    from src.tools import instagram
    try:
        return instagram.connection_status(live=live)
    except Exception as exc:  # noqa: BLE001 - diagnostik tidak boleh 500 mentah
        return {"status": "error", "configured": False,
                "hints": [f"Gagal memeriksa koneksi: {type(exc).__name__}: {exc}"],
                "missing_env": [k for k in instagram.REQUIRED_ENV if not config.opt(k)]}
