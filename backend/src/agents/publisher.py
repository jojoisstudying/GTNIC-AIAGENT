"""AGENT 4: Publisher. Poster dari Designer -> upload -> posting Instagram, DENGAN gerbang persetujuan manusia.
Preflight menolak posting jika ada masalah (placeholder, QC gagal, env kosong, ada intent gantung, dll)."""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from src import config
from src.core.credentials import CredentialExpiredError, ensure_instagram_credentials
from src.core.db import Publication, SessionLocal, sessionmaker
from src.core.events import EventEmitter
from src.tools import asset_library, hosting, instagram

REQUIRED_ENV = ["IG_TOKEN", "IG_USER_ID", "CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"]
PUBLISHED_FILE = config.OUTPUT_DIR / "published.json"


class PendingIntentError(RuntimeError):
    """Raised when there is an unresolved publication intent in the database."""


class QuotaExceededError(RuntimeError):
    """Raised when the Instagram publishing quota has been exceeded."""


def build_caption(plan: dict) -> str:
    tags = " ".join(plan.get("hashtags", []))
    return (plan.get("caption", "").strip() + ("\n\n" + tags if tags else "")).strip()


def check_pending_intent(session: Session) -> Publication | None:
    """Return the most recent unresolved intent row if any exists."""
    stmt = select(Publication).where(Publication.status == "intent").order_by(Publication.id.desc()).limit(1)
    return session.scalar(stmt)


def check_publishing_quota(ctx=None) -> dict:
    """Check Instagram content_publishing_limit before publishing.

    Raises QuotaExceededError if quota is reached.
    """
    try:
        limit_data = instagram.get_content_publishing_limit(ctx=ctx)
        quota_usage = limit_data.get("quota_usage")
        config_info = limit_data.get("config", {})
        quota_total = config_info.get("quota_total")
        if quota_usage is not None and quota_total is not None:
            if quota_usage >= quota_total:
                raise QuotaExceededError(
                    f"Kuota posting Instagram habis ({quota_usage}/{quota_total}). "
                    f"Reset dalam {config_info.get('quota_duration', 86400)} detik."
                )
        return limit_data
    except QuotaExceededError:
        raise
    except Exception:
        # Jika endpoint limit tidak didukung oleh jenis akun atau gagal sementara, lanjutkan dengan warning
        return {}


def preflight(plan_out: dict, design: dict, allow_placeholder: bool = False,
              session: Session | None = None, ctx=None) -> list[str]:
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
    if len(build_caption(plan)) > 2200:
        problems.append("caption + hashtag lebih dari 2200 karakter")
    missing = [k for k in REQUIRED_ENV if not config.opt(k)]
    if missing:
        problems.append(f"env belum diisi di .env: {missing}")

    # Cek status kredensial dan hanging intent di DB
    db_session = session or SessionLocal()
    try:
        hanging = check_pending_intent(db_session)
        if hanging:
            problems.append(f"ada publication intent menggantung (id={hanging.id}, intent_at={hanging.intent_at}). Periksa manual sebelum memposting baru.")
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


def publish(plan: dict, slide_paths: list[str], on_step=print, *, ctx=None,
            session_factory: sessionmaker[Session] = SessionLocal) -> dict:
    session = ctx.session if (ctx and getattr(ctx, "session", None)) else session_factory()
    run_id = getattr(ctx, "run_id", None)
    own_session = not (ctx and getattr(ctx, "session", None))

    # Cek hanging intent dan status kredensial sebelum mulai
    hanging = check_pending_intent(session)
    if hanging:
        if own_session:
            session.close()
        raise PendingIntentError(f"Tolak posting: ada intent menggantung (id={hanging.id}). Periksa manual.")

    # Pastikan kredensial aktif/segar
    ensure_instagram_credentials(session, http=ctx.http if ctx else None,
                                 emitter=ctx.emitter if ctx and hasattr(ctx, "emitter") else None)

    # Pastikan kuota publishing mencukupi
    check_publishing_quota(ctx=ctx)

    caption = build_caption(plan)
    urls = []
    for p in slide_paths:
        on_step(f"[publisher] upload {Path(p).name} ...")
        urls.append(hosting.upload_jpeg(p, http=ctx.http if ctx else None))

    # Tulis status=intent SEBELUM memanggil API Instagram
    now = datetime.now(timezone.utc)
    pub_row = Publication(
        run_id=run_id,
        status="intent",
        intent_at=now,
        caption=caption,
        image_urls_json=json.dumps(urls, ensure_ascii=False)
    )
    session.add(pub_row)
    session.commit()
    if ctx and hasattr(ctx, "emit"):
        ctx.emit("info", "publication_intent", step="publisher", status="intent",
                 detail={"pub_id": pub_row.id, "slide_count": len(urls)})

    try:
        if len(urls) == 1:
            on_step("[publisher] posting 1 gambar ke Instagram ...")
            media_id = instagram.publish_image(urls[0], caption, ctx=ctx)
        else:
            on_step(f"[publisher] posting carousel {len(urls)} slide ke Instagram ...")
            media_id = instagram.publish_carousel(urls, caption, ctx=ctx)

        info = {}
        try:
            info = instagram.get_media_metrics(media_id, ctx=ctx)
        except Exception as e:
            on_step(f"(metrik awal belum bisa dibaca: {e})")

        # Update status ke published setelah sukses
        pub_row.status = "published"
        pub_row.media_id = media_id
        pub_row.permalink = info.get("permalink")
        session.commit()

        if ctx and hasattr(ctx, "emit"):
            ctx.emit("info", "publication_published", step="publisher", status="published",
                     detail={"pub_id": pub_row.id, "media_id": media_id, "permalink": info.get("permalink")})

        record = {"media_id": media_id, "permalink": info.get("permalink"), "posted_at": int(time.time()),
                  "concept": plan.get("concept"), "caption": caption, "image_urls": urls,
                  "schedule_hypothesis": (plan.get("schedule") or {}).get("suggested_time")}
        history = json.loads(PUBLISHED_FILE.read_text(encoding="utf-8")) if PUBLISHED_FILE.exists() else []
        history.append(record)
        PUBLISHED_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
        return record
    except Exception as exc:
        pub_row.status = "failed"
        pub_row.error = str(exc)[:500]
        session.commit()
        if ctx and hasattr(ctx, "emit"):
            ctx.emit("error", "publication_failed", step="publisher", status="failed",
                     detail={"pub_id": pub_row.id, "error": str(exc)[:500]})
        raise
    finally:
        if own_session:
            session.close()


def confirm_and_publish(plan_out: dict, design: dict, yes=False, allow_placeholder=False, dry_run=False,
                        on_step=print, ask=input, *, ctx=None) -> dict:
    plan = plan_out.get("plan") or {}
    print("\n===== PRATINJAU POSTING =====")
    print("Slide :", ", ".join(Path(m["path"]).name for m in design.get("slides", [])), "| lihat:", design.get("preview"))
    print("Caption:\n" + build_caption(plan))
    print("\nSaran jadwal (HIPOTESIS, posting dilakukan SEKARANG bila kamu setuju):",
          (plan.get("schedule") or {}).get("suggested_time"))
    session = ctx.session if (ctx and getattr(ctx, "session", None)) else None
    problems = preflight(plan_out, design, allow_placeholder, session=session, ctx=ctx)
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
