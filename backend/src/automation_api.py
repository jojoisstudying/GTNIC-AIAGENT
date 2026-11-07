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
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from src import config
from src.core import auth, automation, publication_service as ps
from src.core.db import (ContentStrategyItem, PostAnalytics, PostAnalyticsSnapshot, Publication, Run,
                         SessionLocal)
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
    return True if row is None else bool(row.require_approval)


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


@router.get("/runs/{run_id}/publication")
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
        if pub.status == ps.PUBLISHED:
            return {"ok": True, "already_published": True,
                    "publication": _publication_payload(session, pub)}
        if req.scheduled_for:
            try:
                ps.update_draft(session, pub, scheduled_for=_parse_dt(req.scheduled_for))
            except PublicationError as exc:
                raise HTTPException(status_code=exc.status_code, detail=str(exc)) from None
        try:
            ps.approve(session, pub, actor=actor, publish_now=bool(req.publish_now))
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


@router.get("/publications")
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


@router.get("/publications/{pub_id}")
def get_publication(pub_id: int):
    with SessionLocal() as session:
        pub = session.get(Publication, pub_id)
        if not pub:
            raise HTTPException(status_code=404, detail="Publikasi tidak ditemukan")
        return _publication_payload(session, pub)


def _topic_label(session, pub: Publication | None) -> str:
    if pub is None:
        return "-"
    item = session.get(ContentStrategyItem, pub.strategy_item_id) if pub.strategy_item_id else None
    if item and item.topic:
        return item.topic[:120]
    run = session.get(Run, pub.run_id) if pub.run_id else None
    return (run.topic if run else "")[:120] or f"#{pub.id}"


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
    require_approval: Optional[bool] = None
    auto_generate: Optional[bool] = None
    lead_hours: Optional[int] = None


def _automation_payload(session) -> dict:
    row = automation._ensure(session)
    settings = automation.serialize_settings(row)
    nxt = automation.next_slot_after(session)
    return {
        "settings": settings,
        "summary": automation.summary(session),
        "next_slot": nxt.isoformat() if nxt else None,
        "pending_approvals": [_publication_payload(session, p)
                              for p in automation.pending_approvals(session)],
        "scheduled": [_publication_payload(session, p)
                      for p in automation.scheduled_publications(session)],
        "activity": [automation.serialize_event(e) for e in automation.recent_events(session, 25)],
        "scheduler_process_enabled": (config.opt("SCHEDULER_ENABLED", "false").lower() == "true"),
        "server_time": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/automation")
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


@router.get("/automation/activity")
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


@router.get("/analytics/publications")
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


@router.get("/analytics/publications/{pub_id}")
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
    if not config.opt("IG_USER_ID"):
        raise HTTPException(status_code=409, detail="IG_USER_ID belum dikonfigurasi di backend/.env")
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


@router.get("/integrations/instagram/status")
def instagram_integration_status(live: bool = True):
    """Diagnostik kesiapan publikasi Instagram (tanpa mempublikasikan apa pun)."""
    from src.tools import instagram
    try:
        return instagram.connection_status(live=live)
    except Exception as exc:  # noqa: BLE001 - diagnostik tidak boleh 500 mentah
        return {"status": "error", "configured": False,
                "hints": [f"Gagal memeriksa koneksi: {type(exc).__name__}: {exc}"],
                "missing_env": [k for k in instagram.REQUIRED_ENV if not config.opt(k)]}
