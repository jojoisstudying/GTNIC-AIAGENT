"""Alur persetujuan -> publikasi konten ke Instagram/Facebook.

Aturan yang ditegakkan modul ini:

1. **Tidak ada publikasi tanpa persetujuan manusia** (kecuali operator secara eksplisit
   mematikan ``require_approval`` di Pusat Otomatisasi).
2. **Persetujuan tidak diminta berulang.** Menyetujui konten yang sudah disetujui hanya
   mengembalikan baris yang sama (idempoten); UI tidak menampilkan tombol lagi.
3. **Tidak ada publikasi ganda.** Satu konten punya tepat satu ``publications`` per
   platform (``dedupe_key``), dan setiap eksekusi harus *claim* baris secara atomik
   sebelum memanggil API Meta. Klik ganda / retry paralel akan ditolak.
4. **Status tidak pasti tidak diretry otomatis.** Baris berstatus ``intent`` berarti
   API Meta sudah dipanggil tetapi hasilnya belum tercatat; retry otomatis bisa
   menghasilkan dua postingan, jadi perlu rekonsiliasi manusia.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.core.db import Approval, ContentStrategyItem, Publication, PostAnalytics, Run, utc_now

log = logging.getLogger("gtnic.publication")

PENDING_APPROVAL = "pending_approval"
SCHEDULED = "scheduled"
PUBLISHING = "publishing"
INTENT = "intent"
PUBLISHED = "published"
FAILED = "failed"
CANCELLED = "cancelled"

STATUSES = (PENDING_APPROVAL, SCHEDULED, PUBLISHING, INTENT, PUBLISHED, FAILED, CANCELLED)

# Status yang boleh dipindahkan ke CANCELLED (belum tayang).
CANCELLABLE = {PENDING_APPROVAL, SCHEDULED, FAILED}
# Status yang menandakan "jangan sentuh lagi".
IMMUTABLE = {PUBLISHED, INTENT, PUBLISHING}

STATUS_LABELS = {
    PENDING_APPROVAL: "Menunggu persetujuan",
    SCHEDULED: "Dijadwalkan",
    PUBLISHING: "Sedang dipublikasikan",
    INTENT: "Status publikasi belum pasti",
    PUBLISHED: "Berhasil",
    FAILED: "Gagal",
    CANCELLED: "Dibatalkan",
}

MAX_ATTEMPTS = 3
CAPTION_MAX = 2200
HASHTAG_MAX = 30
SUPPORTED_PLATFORMS = {"instagram", "facebook"}
FACEBOOK_SUPPORTED = False  # integrasi Facebook Page belum diimplementasikan


class PublicationError(RuntimeError):
    """Kesalahan yang aman ditampilkan ke pengguna (bukan stack trace)."""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def normalize_hashtags(raw) -> list[str]:
    """Terima list atau string dipisah spasi/koma; hasil selalu '#tag' unik."""
    if raw is None:
        return []
    if isinstance(raw, str):
        items = raw.replace(",", " ").split()
    else:
        items = [str(x) for x in raw]
    out: list[str] = []
    for item in items:
        tag = item.strip()
        if not tag:
            continue
        if not tag.startswith("#"):
            tag = "#" + tag
        tag = "#" + "".join(ch for ch in tag[1:] if ch.isalnum() or ch == "_")
        if len(tag) > 1 and tag.lower() not in (t.lower() for t in out):
            out.append(tag)
    return out


def compose_caption(caption: str, hashtags: list[str]) -> str:
    """Gabungkan caption + hashtag tanpa duplikasi, dipotong ke batas Instagram."""
    body = (caption or "").strip()
    tags = " ".join(hashtags[:HASHTAG_MAX])
    full = f"{body}\n\n{tags}".strip() if tags else body
    if len(full) > CAPTION_MAX:
        room = CAPTION_MAX - (len(tags) + 2 if tags else 0)
        body = body[:max(0, room)].rstrip()
        full = f"{body}\n\n{tags}".strip() if tags else body
    return full[:CAPTION_MAX]


def dedupe_key_for(run_id: str, platform: str = "instagram") -> str:
    return f"{platform}:{run_id}"


def _aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def serialize(pub: Publication) -> dict:
    """Bentuk JSON yang stabil untuk frontend (dipakai semua endpoint publikasi)."""
    try:
        image_urls = json.loads(pub.image_urls_json or "[]")
    except ValueError:
        image_urls = []
    try:
        hashtags = json.loads(pub.hashtags_json or "[]")
    except ValueError:
        hashtags = []
    def _iso(value):
        aware = _aware(value)
        return aware.isoformat() if aware else None

    can_cancel = pub.status in CANCELLABLE
    can_publish = pub.status in (PENDING_APPROVAL, SCHEDULED, FAILED) and not pub.media_id
    return {
        "id": pub.id,
        "run_id": pub.run_id,
        "strategy_item_id": pub.strategy_item_id,
        "platform": pub.platform or "instagram",
        "status": pub.status,
        "status_label": STATUS_LABELS.get(pub.status, pub.status),
        "requires_approval": pub.status == PENDING_APPROVAL,
        "approved_at": _iso(pub.approved_at),
        "approved_by": pub.approved_by,
        "scheduled_for": _iso(pub.scheduled_for),
        "published_at": _iso(pub.published_at),
        "media_id": pub.media_id,
        "media_type": pub.media_type,
        "permalink": pub.permalink,
        "caption": pub.caption,
        "hashtags": hashtags,
        "image_urls": image_urls,
        "publish_attempts": pub.publish_attempts or 0,
        "error": pub.error,
        "can_cancel": can_cancel,
        "can_publish": can_publish,
        "can_edit": pub.status in (PENDING_APPROVAL, SCHEDULED, FAILED),
        "created_at": _iso(pub.created_at),
        "updated_at": _iso(pub.updated_at),
    }


def get_for_run(session: Session, run_id: str, platform: str = "instagram") -> Publication | None:
    return session.scalar(select(Publication).where(
        Publication.run_id == run_id, Publication.platform == platform).order_by(Publication.id.desc()))


def ensure_pending(session: Session, *, run_id: str, plan: dict | None, media_type: str,
                   image_urls: list[str], strategy_item_id: int | None = None,
                   platform: str = "instagram", scheduled_for: datetime | None = None,
                   require_approval: bool = True, actor: str = "api_user") -> Publication:
    """Buat baris publikasi ``pending_approval`` (atau kembalikan yang sudah ada).

    Konten yang sudah pernah dipublikasikan tidak pernah dibuatkan baris baru.
    """
    existing = get_for_run(session, run_id, platform)
    if existing:
        return existing

    plan = plan or {}
    caption = str(plan.get("caption") or "").strip()
    hashtags = normalize_hashtags(plan.get("hashtags"))
    now = utc_now()
    pub = Publication(
        run_id=run_id,
        strategy_item_id=strategy_item_id,
        platform=platform,
        status=SCHEDULED if scheduled_for and not require_approval else PENDING_APPROVAL,
        dedupe_key=dedupe_key_for(run_id, platform),
        media_type=media_type,
        caption=compose_caption(caption, hashtags),
        hashtags_json=json.dumps(hashtags, ensure_ascii=False),
        image_urls_json=json.dumps(image_urls, ensure_ascii=False),
        scheduled_for=scheduled_for,
        approved_at=None if require_approval else now,
        approved_by=None if require_approval else "autopilot",
        created_at=now,
        updated_at=now,
    )
    session.add(pub)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = get_for_run(session, run_id, platform)
        if existing is None:
            raise
        return existing
    log.info("Publikasi %s untuk run %s dibuat (status=%s)", pub.id, run_id, pub.status)
    return pub


def update_draft(session: Session, pub: Publication, *, caption: str | None = None,
                 hashtags=None, scheduled_for: datetime | None = None,
                 clear_schedule: bool = False, image_urls: list[str] | None = None,
                 media_type: str | None = None) -> Publication:
    """Edit caption/hashtag/jadwal/gambar selama konten belum dipublikasikan."""
    if pub.status in IMMUTABLE:
        raise PublicationError(
            f"Konten berstatus '{STATUS_LABELS.get(pub.status, pub.status)}' tidak bisa diedit lagi.",
            status_code=409)
    if caption is not None or hashtags is not None:
        tags = normalize_hashtags(hashtags) if hashtags is not None else json.loads(pub.hashtags_json or "[]")
        body = caption if caption is not None else _caption_body(pub)
        if not body.strip():
            raise PublicationError("Caption tidak boleh kosong.")
        pub.hashtags_json = json.dumps(tags, ensure_ascii=False)
        pub.caption = compose_caption(body, tags)
    if image_urls is not None:
        cleaned = [u for u in image_urls if isinstance(u, str) and u.strip()]
        if not cleaned:
            raise PublicationError("Minimal satu gambar/video harus dipilih.")
        if len(cleaned) > 10:
            raise PublicationError("Carousel Instagram maksimal 10 media.")
        pub.image_urls_json = json.dumps(cleaned, ensure_ascii=False)
    if media_type:
        pub.media_type = media_type
    if clear_schedule:
        pub.scheduled_for = None
        if pub.status == SCHEDULED:
            pub.status = PENDING_APPROVAL
    elif scheduled_for is not None:
        pub.scheduled_for = scheduled_for
        if pub.status in (SCHEDULED, PENDING_APPROVAL) and scheduled_for > utc_now():
            pub.status = SCHEDULED if pub.approved_at else PENDING_APPROVAL
    pub.updated_at = utc_now()
    session.commit()
    return pub


def _caption_body(pub: Publication) -> str:
    """Caption tanpa blok hashtag di akhir (untuk diedit terpisah di UI)."""
    caption = pub.caption or ""
    try:
        tags = json.loads(pub.hashtags_json or "[]")
    except ValueError:
        tags = []
    if tags:
        block = " ".join(tags)
        if caption.endswith(block):
            return caption[: -len(block)].rstrip()
    return caption


def approve(session: Session, pub: Publication, *, actor: str = "api_user",
            publish_now: bool = True) -> Publication:
    """Setujui konten. Idempoten: yang sudah disetujui tidak diproses ulang."""
    if pub.status == PUBLISHED:
        raise PublicationError("Konten ini sudah dipublikasikan.", status_code=409)
    if pub.status == CANCELLED:
        raise PublicationError(
            "Publikasi ini sudah dibatalkan. Buat draf publikasi baru bila ingin memposting ulang.",
            status_code=409)
    if pub.status in (INTENT, PUBLISHING):
        raise PublicationError(
            "Publikasi sedang/berhenti di tengah proses. Periksa postingan di Instagram sebelum mencoba lagi.",
            status_code=409)
    if pub.approved_at is not None and pub.status in (SCHEDULED, PENDING_APPROVAL):
        # Sudah pernah disetujui: perlakukan sebagai lanjutan, bukan persetujuan baru.
        if pub.status == SCHEDULED:
            return pub
    now = utc_now()
    pub.approved_at = pub.approved_at or now
    pub.approved_by = pub.approved_by or actor
    if pub.error:
        pub.error = None
    due_at = _aware(pub.scheduled_for)
    future = due_at is not None and due_at > now
    pub.status = SCHEDULED if (future or not publish_now) else PENDING_APPROVAL
    pub.updated_at = now
    session.add(Approval(
        entity_type="publication",
        entity_id=str(pub.id),
        run_id=pub.run_id,
        decision="approved",
        actor=actor,
        actor_type="human",
        notes=f"{pub.platform} · {'dijadwalkan' if pub.status == SCHEDULED else 'siap dipublikasikan'}",
    ))
    if pub.strategy_item_id:
        item = session.get(ContentStrategyItem, pub.strategy_item_id)
        if item and item.status in {"draft", "awaiting_approval", "approved", "generation_failed"}:
            item.status = "approved_to_publish" if pub.status != SCHEDULED else "scheduled"
            item.approved_by = actor
            item.approval_notes = None
    session.commit()
    log.info("Publikasi %s disetujui oleh %s (status=%s)", pub.id, actor, pub.status)
    return pub


def cancel(session: Session, pub: Publication, *, actor: str = "api_user",
           reason: str = "") -> Publication:
    """Batalkan publikasi yang belum tayang."""
    if pub.status not in CANCELLABLE:
        raise PublicationError(
            f"Tidak bisa dibatalkan: status '{STATUS_LABELS.get(pub.status, pub.status)}'. "
            "Konten yang sudah tayang harus dihapus manual dari aplikasi Instagram.",
            status_code=409)
    pub.status = CANCELLED
    pub.claim_token = None
    pub.claimed_at = None
    pub.error = reason[:500] if reason else pub.error
    pub.updated_at = utc_now()
    session.add(Approval(
        entity_type="publication", entity_id=str(pub.id), run_id=pub.run_id,
        decision="cancelled", actor=actor, actor_type="human", notes=reason[:400] or "Dibatalkan pengguna"))
    if pub.strategy_item_id:
        item = session.get(ContentStrategyItem, pub.strategy_item_id)
        if item and item.status not in {"published", "publishing"}:
            item.status = "rejected"
            item.approval_notes = "Publikasi dibatalkan oleh pengguna"
    session.commit()
    log.info("Publikasi %s dibatalkan oleh %s", pub.id, actor)
    return pub


def claim(session: Session, pub: Publication) -> str:
    """Ambil hak eksekusi secara atomik. Mengembalikan claim token.

    UPDATE bersyarat memastikan hanya satu pemanggil (klik ganda, retry, scheduler)
    yang bisa lanjut. Caller wajib release/commit status akhir setelah selesai.
    """
    if pub.media_id:
        raise PublicationError("Konten ini sudah punya media_id; publikasi ulang diblokir.", status_code=409)
    if pub.publish_attempts and pub.publish_attempts >= MAX_ATTEMPTS:
        raise PublicationError(
            f"Sudah {pub.publish_attempts} kali gagal. Periksa error terakhir lalu batalkan atau perbaiki konten.",
            status_code=409)
    token = uuid.uuid4().hex
    now = utc_now()
    from sqlalchemy import update
    result = session.execute(
        update(Publication)
        .where(Publication.id == pub.id,
               Publication.status.in_((PENDING_APPROVAL, SCHEDULED, FAILED)),
               Publication.claim_token.is_(None),
               Publication.media_id.is_(None))
        .values(status=PUBLISHING, claim_token=token, claimed_at=now,
                publish_attempts=(Publication.publish_attempts or 0) + 1, updated_at=now,
                error=None))
    session.commit()
    if getattr(result, "rowcount", 0) != 1:
        session.refresh(pub)
        raise PublicationError(
            f"Publikasi ini sedang diproses atau sudah selesai (status '{STATUS_LABELS.get(pub.status, pub.status)}'). "
            "Muat ulang halaman untuk melihat status terbaru.",
            status_code=409)
    session.refresh(pub)
    return token


def mark_intent(session: Session, pub: Publication, token: str) -> None:
    """Tandai 'sudah memanggil API Meta'. Retry otomatis diblokir setelah titik ini."""
    if pub.claim_token != token:
        raise PublicationError("Klaim publikasi tidak valid (diproses proses lain).", status_code=409)
    pub.status = INTENT
    pub.intent_at = utc_now()
    pub.updated_at = utc_now()
    session.commit()


def mark_published(session: Session, pub: Publication, *, media_id: str, permalink: str | None,
                   media_type: str | None = None) -> Publication:
    pub.status = PUBLISHED
    pub.media_id = media_id
    pub.permalink = permalink
    pub.media_type = media_type or pub.media_type
    pub.published_at = utc_now()
    pub.updated_at = utc_now()
    pub.claim_token = None
    pub.claimed_at = None
    pub.error = None
    if pub.strategy_item_id:
        item = session.get(ContentStrategyItem, pub.strategy_item_id)
        if item:
            item.status = "published"
            item.approval_notes = None
    if pub.run_id:
        run_row = session.get(Run, pub.run_id)
        if run_row and run_row.status == "awaiting_approval":
            run_row.status = "ok"
    session.add(Approval(
        entity_type="publication", entity_id=str(pub.id), run_id=pub.run_id,
        decision="published", actor="system", actor_type="system",
        notes=f"media_id={media_id}"))
    session.commit()
    return pub


def mark_failed(session: Session, pub: Publication, error: str) -> Publication:
    pub.status = FAILED
    pub.error = (error or "Publikasi gagal")[:1000]
    pub.claim_token = None
    pub.claimed_at = None
    pub.updated_at = utc_now()
    if pub.strategy_item_id:
        item = session.get(ContentStrategyItem, pub.strategy_item_id)
        if item and item.status != "published":
            item.status = "publication_failed"
            item.approval_notes = pub.error[:500]
    session.commit()
    return pub


def ensure_analytics_row(session: Session, pub: Publication, *, topic: str, content_pillar: str,
                         fmt: str) -> PostAnalytics:
    """Siapkan baris analytics (metrik NULL = belum diambil, bukan nol)."""
    row = session.scalar(select(PostAnalytics).where(PostAnalytics.publication_id == pub.id))
    if row is None:
        row = PostAnalytics(
            publication_id=pub.id,
            run_id=pub.run_id,
            strategy_item_id=pub.strategy_item_id,
            media_id=pub.media_id,
            permalink=pub.permalink,
            format=fmt,
            content_pillar=content_pillar,
            topic=topic,
            source="instagram_api_pending_metrics",
            ingestion_status="pending",
            is_simulated=False,
        )
        session.add(row)
    else:
        row.media_id = pub.media_id or row.media_id
        row.permalink = pub.permalink or row.permalink
        row.format = fmt or row.format
    session.commit()
    return row


def release_stale_claims(session: Session, *, older_than_minutes: int = 30) -> int:
    """Kembalikan baris 'publishing' yang process-nya mati ke 'failed' (aman: API belum dipanggil)."""
    from datetime import timedelta
    from sqlalchemy import update
    cutoff = utc_now() - timedelta(minutes=older_than_minutes)
    res = session.execute(
        update(Publication)
        .where(Publication.status == PUBLISHING,
               Publication.claimed_at.is_not(None),
               Publication.claimed_at < cutoff)
        .values(status=FAILED, claim_token=None,
                error="Proses publikasi berhenti sebelum menghubungi Instagram. Silakan coba lagi.",
                updated_at=utc_now()))
    session.commit()
    return getattr(res, "rowcount", 0) or 0
