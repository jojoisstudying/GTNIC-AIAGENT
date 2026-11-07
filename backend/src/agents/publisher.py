"""AGENT 4: Publisher. Poster dari Designer -> upload -> posting Instagram, DENGAN gerbang persetujuan manusia.

Perubahan penting dibanding versi lama:
- Baris ``publications`` sekarang punya alur status eksplisit
  (pending_approval -> scheduled -> publishing -> intent -> published/failed/cancelled)
  sehingga UI bisa menampilkan "Menunggu Persetujuan / Dijadwalkan / Sedang Dipublikasikan /
  Berhasil / Gagal" dan tombol Batalkan Publikasi.
- ``intent`` tetap ada: ditulis SEBELUM memanggil API Meta agar proses yang mati di tengah
  tidak pernah diretry otomatis (mencegah publikasi ganda).
- Error provider disimpan apa adanya (ter-redaksi) supaya penyebab seperti clock skew
  Cloudinary atau izin Meta terlihat oleh operator.
"""
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from src import config
from src.core import publication_service as ps
from src.core.credentials import CredentialExpiredError, ensure_instagram_credentials
from src.core.db import Publication, SessionLocal, sessionmaker
from src.core.events import EventEmitter
from src.carousel.tools import asset_library
from src.tools import hosting, instagram

REQUIRED_ENV = ["IG_TOKEN", "IG_USER_ID", "CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"]
PUBLISHED_FILE = config.OUTPUT_DIR / "published.json"


class PendingIntentError(RuntimeError):
    """Raised when there is an unresolved publication intent in the database."""


class QuotaExceededError(RuntimeError):
    """Raised when the Instagram publishing quota has been exceeded."""


def build_caption(plan: dict) -> str:
    plan = plan or {}
    return ps.compose_caption(plan.get("caption", ""), ps.normalize_hashtags(plan.get("hashtags")))


def check_pending_intent(session: Session) -> Publication | None:
    """Return the most recent unresolved intent row if any exists.

    Hanya baris milik run lain yang menghalangi: run yang sedang diproses punya baris
    intent-nya sendiri dan tidak boleh memblokir dirinya.
    """
    stmt = select(Publication).where(Publication.status == ps.INTENT).order_by(Publication.id.desc()).limit(1)
    return session.scalar(stmt)


def check_publishing_quota(ctx=None) -> dict:
    """Check Instagram content_publishing_limit before publishing.

    Raises QuotaExceededError if quota is reached.
    """
    try:
        limit_data = instagram.get_content_publishing_limit(ctx=ctx)
        quota_usage = limit_data.get("quota_usage")
        config_info = limit_data.get("config", {}) or {}
        quota_total = config_info.get("quota_total")
        if quota_usage is not None and quota_total is not None and quota_usage >= quota_total:
            raise QuotaExceededError(
                f"Kuota posting Instagram habis ({quota_usage}/{quota_total}). "
                f"Reset dalam {config_info.get('quota_duration', 86400)} detik."
            )
        return limit_data
    except QuotaExceededError:
        raise
    except Exception:
        # Endpoint limit tidak didukung/gagal sementara: jangan blokir publikasi.
        return {}


def _hashtag_count(caption: str) -> int:
    return len(re.findall(r"#\w+", caption or ""))


def preflight(plan_out: dict, design: dict, allow_placeholder: bool = False,
              session: Session | None = None, ctx=None, *, run_id: str | None = None) -> list[str]:
    problems = []
    # Normalisasi format plan: baik {"ok": true, "plan": {...}} maupun langsung payload {...}
    plan = plan_out.get("plan") if "plan" in plan_out else plan_out
    if "ok" in plan_out and not plan_out.get("ok"):
        problems.append(f"rencana belum lolos validasi: {plan_out.get('issues')}")
    if not design.get("ok"):
        bad = [f"slide {m['index']}: {m['issues']}" for m in design.get("slides", []) if m.get("issues")]
        problems.append(f"QC desain belum lolos: {bad or design.get('warnings')}")
    slides = design.get("slides", [])
    pending = asset_library.pending_assets()
    if pending:
        problems.append("asset foto masih pending review: " + ", ".join(str(a["id"]) for a in pending))
    if not 1 <= len(slides) <= 10:
        problems.append(f"jumlah slide {len(slides)} di luar 1-10")
    for m in slides:
        if not Path(m["path"]).is_file():
            problems.append(f"file hilang: {m['path']}")
        if m.get("has_photo") and (not m.get("photo_path") or not asset_library.is_cutout(m["photo_path"])):
            problems.append(f"slide {m['index']}: foto belum cutout transparan yang tervalidasi")
    if any(m.get("placeholder") for m in slides) and not allow_placeholder:
        problems.append("poster memakai FOTO PLACEHOLDER (tambah --allow-placeholder hanya untuk tes di akun demo)")
    caption = build_caption(plan)
    if len(caption) > ps.CAPTION_MAX:
        problems.append(f"caption + hashtag lebih dari {ps.CAPTION_MAX} karakter")
    if _hashtag_count(caption) > ps.HASHTAG_MAX:
        problems.append(f"lebih dari {ps.HASHTAG_MAX} hashtag (batas Instagram)")
    missing = [k for k in REQUIRED_ENV if not config.opt(k)]
    if missing:
        problems.append(f"env belum diisi di .env: {missing}")

    db_session = session or SessionLocal()
    try:
        hanging = check_pending_intent(db_session)
        if hanging and hanging.run_id != run_id:
            problems.append(f"ada publication intent menggantung (id={hanging.id}, intent_at={hanging.intent_at}). "
                            "Periksa manual sebelum memposting baru.")
        try:
            ensure_instagram_credentials(db_session)
        except CredentialExpiredError as err:
            problems.append(f"kredensial Instagram bermasalah: {err}")
        try:
            check_publishing_quota(ctx=ctx)
        except QuotaExceededError as err:
            problems.append(str(err))
    finally:
        if session is None:
            db_session.close()

    return problems


# ---------------------------------------------------------------------------
# Eksekusi publikasi (satu jalur untuk manual, autopilot, dan scheduler)
# ---------------------------------------------------------------------------

def execute_publication(pub_id: int, *, on_step=print, ctx=None, share_to_feed: bool = True,
                        session_factory: sessionmaker[Session] | None = None) -> dict:
    """Publikasikan baris ``publications`` yang sudah disetujui.

    Alur: validasi status -> claim atomik -> upload media (Cloudinary) -> intent ->
    Instagram API -> published/failed. Pemanggil hanya boleh memanggil ini untuk baris
    yang statusnya sudah disetujui (``approved_at`` terisi) atau dijadwalkan.
    """
    # Resolve factory saat dipanggil, bukan saat import: modul ini bisa diarahkan ke
    # session factory lain (tes/multi-DB) tanpa efek samping default argument yang terkunci.
    session_factory = session_factory or SessionLocal
    session = ctx.session if (ctx and getattr(ctx, "session", None)) else session_factory()
    own_session = not (ctx and getattr(ctx, "session", None))
    try:
        pub = session.get(Publication, pub_id)
        if pub is None:
            raise ps.PublicationError("Data publikasi tidak ditemukan.", status_code=404)
        if pub.status == ps.PUBLISHED:
            return {"ok": True, "status": ps.PUBLISHED, "media_id": pub.media_id,
                    "permalink": pub.permalink, "already_published": True}
        if pub.status in (ps.INTENT, ps.PUBLISHING):
            raise ps.PublicationError(
                "Publikasi ini sudah/sedang diproses. Periksa Instagram sebelum mencoba lagi.",
                status_code=409)
        if pub.approved_at is None:
            raise ps.PublicationError("Konten belum disetujui; publikasi diblokir.", status_code=409)
        if pub.platform != "instagram":
            raise ps.PublicationError(
                f"Platform '{pub.platform}' belum didukung untuk publikasi otomatis.", status_code=400)

        # Klaim atomik: klik ganda / retry paralel tidak bisa lanjut bersamaan.
        token = ps.claim(session, pub)
        pub = session.get(Publication, pub_id)
        if ctx and hasattr(ctx, "emit"):
            ctx.emit("info", "publication_intent", step="publisher", status=ps.PUBLISHING,
                     detail={"pub_id": pub.id, "media_type": pub.media_type,
                             "format": "reel" if pub.media_type == "reel" else (pub.media_type or "carousel")})

        try:
            ensure_instagram_credentials(session, http=ctx.http if ctx else None,
                                         emitter=getattr(ctx, "emitter", None))
            session.commit()
            check_publishing_quota(ctx=ctx)

            on_step(f"[publisher] publikasi #{pub.id} ({pub.media_type or 'carousel'}) ...")
            # URL publik disiapkan SEBELUM intent: kalau upload Cloudinary gagal, status
            # tetap bisa dikembalikan ke 'failed' tanpa baris intent menggantung.
            urls = _ensure_public_media(pub, ctx=ctx, on_step=on_step, session=session)

            # Titik tidak-bisa-kembali: tandai intent SEBELUM memanggil API Meta.
            ps.mark_intent(session, pub, token)
            pub = session.get(Publication, pub_id)

            media_type = (pub.media_type or ("reel" if urls and _looks_like_video(urls[0]) else "carousel")).lower()
            if media_type == "reel" or (urls and _looks_like_video(urls[0])):
                on_step("[publisher] memposting Reels (pemrosesan video 1-3 menit) ...")
                media_id = instagram.publish_reel(urls[0], pub.caption, share_to_feed=share_to_feed, ctx=ctx)
                media_type = "reel"
            elif len(urls) == 1:
                on_step("[publisher] memposting 1 gambar ...")
                media_id = instagram.publish_image(urls[0], pub.caption, ctx=ctx)
                media_type = "image"
            else:
                on_step(f"[publisher] memposting carousel {len(urls)} slide ...")
                media_id = instagram.publish_carousel(urls, pub.caption, ctx=ctx)
                media_type = "carousel"
        except Exception as exc:
            session.rollback()
            pub = session.get(Publication, pub_id)
            if pub is not None and pub.status in (ps.PUBLISHING, ps.INTENT):
                ps.mark_failed(session, pub, _describe(exc))
            if ctx and hasattr(ctx, "emit"):
                ctx.emit("error", "publication_failed", step="publisher", status="failed",
                         detail={"pub_id": pub_id, "error": _describe(exc)})
            # Pesan provider diteruskan apa adanya (sudah ter-redaksi di lapisan HTTP) supaya
            # operator melihat penyebab sebenarnya, bukan "HTTP request failed" generik.
            if isinstance(exc, ps.PublicationError):
                raise
            raise ps.PublicationError(_describe(exc), status_code=502) from None

        # 3) Sukses: simpan media_id + permalink, siapkan baris analytics (metrik NULL).
        permalink = None
        try:
            info = instagram.get_media_metrics(media_id, ctx=ctx)
            permalink = info.get("permalink")
        except Exception as exc:  # noqa: BLE001 - permalink opsional
            on_step(f"(permalink belum bisa dibaca: {exc})")
        ps.mark_published(session, pub, media_id=media_id, permalink=permalink, media_type=media_type)
        pub = session.get(Publication, pub_id)
        try:
            ps.ensure_analytics_row(session, pub, topic=_topic_of(pub),
                                    content_pillar=_pillar_of(session, pub), fmt=media_type)
        except Exception as exc:  # noqa: BLE001 - postingan sudah tayang; kegagalan catat metrik harus terlihat
            # Jangan sembunyikan: media sudah tayang tapi pencatatan analytics gagal -> operator wajib tahu.
            raise ps.PublicationError(
                f"Konten sudah tayang (media_id={media_id}) tetapi pencatatan analytics gagal: "
                f"{type(exc).__name__}: {exc}", status_code=500) from None
        _append_history(pub)
        if ctx and hasattr(ctx, "emit"):
            ctx.emit("info", "publication_published", step="publisher", status="published",
                     detail={"pub_id": pub.id, "media_id": media_id, "permalink": permalink})
        result = {"ok": True, "status": ps.PUBLISHED, "media_id": media_id, "permalink": permalink,
                  "format": media_type, "media_type": media_type, "publication_id": pub.id}
        if media_type == "reel":
            result["video_url"] = (urls or [None])[0]
        return result
    finally:
        if own_session:
            session.close()


def _describe(exc: Exception) -> str:
    text = str(exc)
    if isinstance(exc, ps.PublicationError):
        return text
    return f"{type(exc).__name__}: {text}" if type(exc).__name__ not in ("RuntimeError",) else text


def _looks_like_video(url: str) -> bool:
    return url.split("?")[0].lower().endswith((".mp4", ".mov"))


def _topic_of(pub: Publication) -> str:
    """Topik konten dari tabel runs (untuk label analytics)."""
    if not pub.run_id:
        return ""
    try:
        from src.core.db import Run, SessionLocal
        with SessionLocal() as s:
            run = s.get(Run, pub.run_id)
            return (run.topic if run else "") or ""
    except Exception:  # pragma: no cover - label bersifat opsional
        return ""


def _pillar_of(session: Session, pub: Publication) -> str:
    from src.core.db import ContentStrategyItem
    if pub.strategy_item_id:
        item = session.get(ContentStrategyItem, pub.strategy_item_id)
        if item and item.content_pillar:
            return item.content_pillar
    return "Belum diklasifikasikan"


def _ensure_public_media(pub: Publication, *, ctx=None, on_step=print, session=None) -> list[str]:
    """Pastikan setiap media punya URL publik JPEG/MP4 (upload ke Cloudinary bila perlu)."""
    try:
        urls = json.loads(pub.image_urls_json or "[]")
    except ValueError:
        urls = []
    urls = [u for u in urls if isinstance(u, str)]
    if not urls:
        local = (pub.caption or "").strip()  # tidak ada; pesan jelas lebih baik daripada crash
        raise ps.PublicationError(
            "Tidak ada media untuk dipublikasikan. Buat ulang konten atau unggah gambar.", status_code=400)
    public: list[str] = []
    for url in urls:
        if url.startswith(("http://", "https://")):
            public.append(url)
            continue
        path = Path(url)
        on_step(f"[publisher] upload {path.name} ke Cloudinary ...")
        try:
            if path.suffix.lower() in (".mp4", ".mov"):
                public.append(hosting.upload_video(str(path), http=ctx.http if ctx else None))
            else:
                public.append(hosting.upload_jpeg(str(path), http=ctx.http if ctx else None))
        except hosting.CloudinaryError as exc:
            raise ps.PublicationError(f"Upload media gagal: {exc}", status_code=502) from None
    session and session.commit()
    pub.image_urls_json = json.dumps(public, ensure_ascii=False)
    if session:
        session.commit()
    return public


def _append_history(pub: Publication) -> None:
    try:
        record = {"media_id": pub.media_id, "permalink": pub.permalink, "posted_at": int(time.time()),
                  "publication_id": pub.id, "run_id": pub.run_id, "platform": pub.platform,
                  "format": pub.media_type, "caption": (pub.caption or "")[:400]}
        history = json.loads(PUBLISHED_FILE.read_text(encoding="utf-8")) if PUBLISHED_FILE.exists() else []
        if not isinstance(history, list):
            history = []
        history.append(record)
        PUBLISHED_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:  # best-effort mirror; database tetap sumber kebenaran
        pass


# ---------------------------------------------------------------------------
# Jalur lama (dipakai script CLI & tes) — tetap melewati gerbang persetujuan
# ---------------------------------------------------------------------------

def publish(plan: dict, slide_paths: list[str], on_step=print, *, ctx=None,
            session_factory: sessionmaker[Session] | None = None) -> dict:
    """Publikasi carousel dari path lokal. Membuat/menyetujui baris publikasi lalu mengeksekusi."""
    session_factory = session_factory or SessionLocal
    session = ctx.session if (ctx and getattr(ctx, "session", None)) else session_factory()
    own_session = not (ctx and getattr(ctx, "session", None))
    run_id = getattr(ctx, "run_id", None)
    try:
        # Intent menggantung dari run LAIN = status Meta tidak pasti -> jangan tambah postingan baru.
        hanging = check_pending_intent(session)
        if hanging and hanging.run_id != (run_id or f"adhoc-{int(time.time())}"):
            raise PendingIntentError(
                f"Tolak posting: ada intent menggantung (id={hanging.id}). Periksa manual.")
        ensure_instagram_credentials(session, http=ctx.http if ctx else None,
                                     emitter=getattr(ctx, "emitter", None))
        session.commit()
        check_publishing_quota(ctx=ctx)

        pub = ps.ensure_pending(session, run_id=run_id or f"adhoc-{int(time.time())}", plan=plan,
                                media_type="carousel" if len(slide_paths) > 1 else "image",
                                image_urls=list(slide_paths), require_approval=False, actor="cli")
        if pub.status != ps.SCHEDULED:
            ps.approve(session, pub, actor="cli", publish_now=True)
            pub = session.get(Publication, pub.id)
            pub.status = ps.SCHEDULED  # langsung dieksekusi di bawah (klaim butuh status siap)
            session.commit()
        result = execute_publication(pub.id, on_step=on_step, ctx=ctx, session_factory=session_factory)
        return {"ok": True, "media_id": result.get("media_id"), "permalink": result.get("permalink"),
                "pub_id": pub.id, "status": ps.PUBLISHED}
    finally:
        if own_session:
            session.close()


def preflight_video(video: dict, caption: str, *, run_id: str | None = None,
                    session: Session | None = None, ctx=None) -> list[str]:
    """Gerbang sebelum posting Reels. Daftar kosong = boleh diposting."""
    from src.video import reel_check

    problems: list[str] = []
    if not video.get("ok"):
        problems.append(f"video belum lolos QC: {video.get('issues') or 'alasan tidak diketahui'}")
    problems.extend(reel_check.check_reel_compat(video.get("video_path")))

    caption = (caption or "").strip()
    if not caption:
        problems.append("caption kosong")
    if len(caption) > ps.CAPTION_MAX:
        problems.append(f"caption lebih dari {ps.CAPTION_MAX} karakter")
    if _hashtag_count(caption) > ps.HASHTAG_MAX:
        problems.append(f"lebih dari {ps.HASHTAG_MAX} hashtag (batas Instagram)")

    missing = [k for k in REQUIRED_ENV if not config.opt(k)]
    if missing:
        problems.append(f"env belum diisi di .env: {missing}")

    db_session = session or SessionLocal()
    try:
        if run_id:
            done = db_session.scalar(select(Publication).where(
                Publication.run_id == run_id, Publication.status == ps.PUBLISHED))
            if done:
                problems.append(f"run ini sudah dipublish (media_id={done.media_id}); buat run baru untuk posting lagi")
        hanging = check_pending_intent(db_session)
        if hanging and hanging.run_id != run_id:
            problems.append(f"ada publication intent menggantung (id={hanging.id}, intent_at={hanging.intent_at}). "
                            "Periksa manual sebelum memposting baru.")
        try:
            ensure_instagram_credentials(db_session)
        except CredentialExpiredError as err:
            problems.append(f"kredensial Instagram bermasalah: {err}")
        try:
            check_publishing_quota(ctx=ctx)
        except QuotaExceededError as err:
            problems.append(str(err))
    finally:
        if session is None:
            db_session.close()
    return problems


def publish_reel(video_path: str, caption: str, on_step=print, *, share_to_feed: bool = True, ctx=None,
                 session_factory: sessionmaker[Session] | None = None) -> dict:
    """Publikasi Reels dari path lokal lewat alur persetujuan yang sama."""
    session_factory = session_factory or SessionLocal
    session_factory = session_factory or SessionLocal
    session = ctx.session if (ctx and getattr(ctx, "session", None)) else session_factory()
    own_session = not (ctx and getattr(ctx, "session", None))
    run_id = getattr(ctx, "run_id", None) or f"adhoc-reel-{int(time.time())}"
    try:
        # Intent menggantung dari run LAIN = status Meta tidak pasti -> jangan tambah postingan baru.
        hanging = check_pending_intent(session)
        if hanging and hanging.run_id != run_id:
            raise PendingIntentError(
                f"Tolak posting: ada intent menggantung (id={hanging.id}). Periksa manual.")
        ensure_instagram_credentials(session, http=ctx.http if ctx else None,
                                     emitter=getattr(ctx, "emitter", None))
        check_publishing_quota(ctx=ctx)
        session.commit()
        # Upload SEBELUM membuat baris publikasi: kegagalan Cloudinary tidak boleh meninggalkan
        # baris intent menggantung (status Meta masih pasti: belum ada panggilan apa pun).
        video_url = video_path if str(video_path).startswith(("http://", "https://")) else \
            hosting.upload_video(str(video_path), http=ctx.http if ctx else None)
        pub = ps.ensure_pending(session, run_id=run_id, plan={"caption": caption},
                                media_type="reel", image_urls=[video_url], require_approval=False,
                                actor="cli")
        if pub.status != ps.SCHEDULED:
            ps.approve(session, pub, actor="cli", publish_now=True)
            pub = session.get(Publication, pub.id)
            pub.status = ps.SCHEDULED
            session.commit()
        return execute_publication(pub.id, on_step=on_step, ctx=ctx, share_to_feed=share_to_feed,
                                   session_factory=session_factory)
    finally:
        if own_session:
            session.close()


def default_video_caption(topic: str, brand: dict | None = None) -> str:
    """Draf caption Reels: topik + ajakan + hashtag brand (jika `hashtags` diisi di brand.json).
    Hanya saran awal; teks final diedit manusia di UI sebelum diposting."""
    brand = brand or {}
    tags = " ".join(t if t.startswith("#") else f"#{t}" for t in (brand.get("hashtags") or []))
    parts = [str(topic).strip(), "Simpan dan bagikan ke temanmu yang butuh ini."]
    if tags:
        parts.append(tags)
    return "\n\n".join(p for p in parts if p)


def confirm_and_publish(plan_out: dict, design: dict, yes=False, allow_placeholder=False, dry_run=False,
                        on_step=print, ask=input, *, ctx=None) -> dict:
    plan = plan_out.get("plan") or {}
    print("\n===== PRATINJAU POSTING =====")
    print("Slide :", ", ".join(Path(m["path"]).name for m in design.get("slides", [])),
          "| lihat:", design.get("preview"))
    print("Caption:\n" + build_caption(plan))
    print("\nSaran jadwal (HIPOTESIS, posting dilakukan SEKARANG bila kamu setuju):",
          (plan.get("schedule") or {}).get("suggested_time"))
    session = ctx.session if (ctx and getattr(ctx, "session", None)) else None
    problems = preflight(plan_out, design, allow_placeholder, session=session, ctx=ctx,
                         run_id=getattr(ctx, "run_id", None))
    if problems:
        print("\nTIDAK BISA DIPOSTING:")
        for p in problems:
            print(" -", p)
        return {"ok": False, "problems": problems}
    if dry_run:
        print("\n[dry-run] semua pemeriksaan lolos, tidak ada yang diposting.")
        return {"ok": True, "dry_run": True}
    if not yes and ask("\nKetik POST (huruf besar) untuk memposting ke Instagram: ").strip() != "POST":
        print("Dibatalkan, tidak ada yang diposting.")
        return {"ok": False, "cancelled": True}
    rec = publish(plan, [m["path"] for m in design["slides"]], on_step, ctx=ctx)
    print("\nTerposting! media_id:", rec["media_id"], "| link:", rec.get("permalink"))
    return {"ok": True, "record": rec}
