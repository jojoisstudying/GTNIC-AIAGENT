"""FastAPI entrypoint for Social Media Automation AI Agent.

Provides endpoints for frontend dashboard integration:
- Trigger run (Research -> Plan -> Design)
- Run status & events monitoring (polling / event stream)
- Layout catalog listing
- Direct publishing to Instagram
- Static asset / slide image preview serving
"""
import logging
import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, desc, func

from src import config
from src.carousel import pipeline
from src.core import auth
from src.core.db import EnterpriseProfile, EnterpriseProfileVersion, ContentStrategyItem, PostAnalytics, AnalyticsInsight
from src.core.strategy import (
    get_or_create_enterprise_profile, calculate_profile_completeness, CALENDAR_STATES, CALENDAR_TRANSITIONS,
    generate_7day_strategy, seed_demo_analytics_data
)

from src.core.context import create_run_context
from src.core.db import Campaign, Run, Plan, Design, Event, Publication, SessionLocal
from src.carousel.layouts import registry

log = logging.getLogger("gtnic.api")

@asynccontextmanager
async def lifespan(_app):
    environment = os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "development")).strip().lower()
    if environment in {"production", "prod"} and not auth.get_configured_api_key():
        raise RuntimeError("GTNIC_API_KEY must be configured before production startup.")
    logging.basicConfig(level=config.opt("LOG_LEVEL", "INFO").upper(),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # Buat tabel yang belum ada + kolom baru (idempotent).
    if config.opt("AUTO_CREATE_SCHEMA", "true").lower() != "false":
        from src.core.db import engine, ensure_schema
        ensure_schema(engine)
    task = None
    if config.opt("SCHEDULER_ENABLED", "false").lower() == "true":
        from src.core.scheduler import scheduler_loop
        from src.core.analytics_ingest import ingest_all
        interval = int(config.opt("SCHEDULER_INTERVAL_SECONDS", "60") or 60)
        ingest_fn = (lambda: ingest_all(SessionLocal)) if config.opt("IG_USER_ID") else None
        task = asyncio.create_task(scheduler_loop(
            SessionLocal, publish_run_to_instagram, interval,
            int(config.opt("ANALYTICS_INGEST_INTERVAL_SECONDS", "21600") or 21600), ingest_fn))
    try:
        yield
    finally:
        if task:
            task.cancel()


from src.ops_api import router as ops_router  # noqa: E402
from src.campaign_api import router as campaign_router  # noqa: E402
import src.core.notify  # noqa: E402,F401  (registrasi listener notifikasi/audit)

app = FastAPI(
    title="GTNIC Social Media AI Agent API",
    version="1.0.0",
    description="Enterprise-grade AI Social Media Post Generator (No AI Slop)",
    lifespan=lifespan,
)

# Enable CORS for Frontend development (Next.js/Vite/localhost)
allowed_origins_env = config.opt("CORS_ORIGINS", "")
allowed_origins = [o.strip() for o in allowed_origins_env.split(",") if o.strip()] if allowed_origins_env else [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
if "*" in allowed_origins:
    raise RuntimeError("CORS_ORIGINS tidak boleh berisi wildcard '*'.")

app.include_router(ops_router)
app.include_router(campaign_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount outputs/slides and gallery directories so frontend can display generated images directly
config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
slides_dir = config.OUTPUT_DIR / "slides"
slides_dir.mkdir(parents=True, exist_ok=True)
reels_dir = config.OUTPUT_DIR / "reels"
reels_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static/output", StaticFiles(directory=str(config.OUTPUT_DIR)), name="output")
app.mount("/static/gallery", StaticFiles(directory=str(config.ROOT / "gallery")), name="gallery")
app.mount("/static/assets", StaticFiles(directory=str(config.ROOT / "assets")), name="brand_assets")
app.mount("/static/data", StaticFiles(directory=str(config.ROOT / "data")), name="data_assets")


# --- Request & Response Models ---

class TriggerRunRequest(BaseModel):
    topic: str = Field(..., description="Topik atau tema konten media sosial yang ingin dibuat")
    fresh: bool = Field(True, description="True untuk melakukan riset web baru (Tavily), False untuk pakai cache")
    include_design: bool = Field(True, description="True untuk merender gambar carousel (Playwright/HTML)")


class VideoRunRequest(BaseModel):
    topic: str = Field(..., description="Topik video Reels / Shorts")
    target_duration: int = Field(30, ge=15, le=60, description="Target durasi video dalam detik (15-60)")
    fresh: bool = Field(True, description="True = riset fakta baru lewat Tavily; False = pakai riset tersimpan (24 jam) bila ada")


class PublishOptions(BaseModel):
    caption: Optional[str] = Field(None, description="Caption final (Reels). Kosong = pakai draf otomatis")
    share_to_feed: bool = Field(True, description="Reels juga tampil di feed profil")


class AssetUploadRequest(BaseModel):
    tags: str = Field(..., description="Comma-separated tags (mis. senyum, formal, pointing)")
    description: str = Field("", description="Deskripsi aset atau figur")


class RegeneratePoseRequest(BaseModel):
    run_id: Optional[str] = Field(None, description="Run yang menunggu pose ini; default: run asal aset")
    prompt: str = Field("", description="Arahan pose kustom (opsional, wajib untuk pose tanpa arahan bawaan)")


class PublishRequest(BaseModel):
    run_id: str = Field(..., description="UUID hex dari run yang ingin dipublish")


class BrandUpdateRequest(BaseModel):
    company: Optional[str] = None
    industry: Optional[str] = None
    description: Optional[str] = None
    audience: Optional[str] = None
    phone: Optional[str] = None
    handle: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    accent_color: Optional[str] = None


# --- Background Pipeline Execution ---

def _execute_pipeline_task(run_id: str, topic: str, fresh: bool, include_design: bool):
    """Worker task executing agent pipeline with proper DB state tracking."""
    brand = pipeline.load_brand()
    ctx = create_run_context(topic, brand, run_id=run_id)
    try:
        pipeline.run(topic, fresh=fresh, ctx=ctx, include_design=include_design)
    except Exception as e:
        log.error(f"[API ERROR] Pipeline execution failed for run {run_id}: {e}")
    finally:
        ctx.close()


def _execute_resume_task(run_id: str):
    """Worker task to resume run after assets have been approved."""
    from src.carousel.agents import designer
    with SessionLocal() as session:
        run = session.get(Run, run_id)
        if not run:
            return
        if run.status == "qc_failed":
            return
        plan_row = session.scalars(
            select(Plan).where(Plan.run_id == run_id).order_by(desc(Plan.version))
        ).first()
        if not plan_row:
            return
        plan = json.loads(plan_row.plan_json)
        brand = pipeline.load_brand()

    ctx = create_run_context(run.topic, brand, run_id=run_id)
    ctx.llm.tokens_in = run.tokens_in or 0
    ctx.llm.tokens_out = run.tokens_out or 0
    ctx.llm.cost_usd = run.cost_usd or 0.0

    try:
        qc = pipeline.check_carousel_semantics(plan, brand=brand, topic=run.topic)
        if not qc.get("ok"):
            with SessionLocal() as session:
                run_row = session.get(Run, run_id)
                if run_row:
                    run_row.status = "qc_failed"
                    run_row.error = "; ".join(qc.get("errors", []))
                    run_row.finished_at = datetime.now(timezone.utc)
                    session.commit()
            ctx.emit("error", "semantic_qc_failed_on_resume", step="qc", status="failed",
                     detail={"errors": qc.get("errors", []), "warnings": qc.get("warnings", [])})
            return
        design_result = designer.run(plan, brand, config.OUTPUT_DIR / "runs" / run_id / "slides", ctx=ctx)
        design_result["semantic_qc"] = qc
        with SessionLocal() as session:
            design_version = session.scalar(
                select(func.max(Design.version)).where(Design.run_id == run_id)
            ) or 0
            design_row = Design(
                run_id=run_id,
                plan_id=plan_row.id,
                version=design_version + 1,
                ok=bool(design_result.get("ok")),
                result_json=json.dumps(design_result, ensure_ascii=False),
                preview_path=design_result.get("preview"),
                semantic_qc_json=json.dumps(qc, ensure_ascii=False),
            )
            session.add(design_row)

            run_row = session.get(Run, run_id)
            if design_result.get("pending_review"):
                run_row.status = "awaiting_approval"
            elif design_result.get("missing_poses"):
                run_row.status = "awaiting_assets"
            elif design_result.get("ok"):
                run_row.status = "awaiting_approval"
            else:
                run_row.status = "ok"
            run_row.finished_at = datetime.now(timezone.utc)
            run_row.error = None  # error lama (mis. regenerate pose gagal) sudah tidak relevan
            run_row.tokens_in = ctx.llm.tokens_in
            run_row.tokens_out = ctx.llm.tokens_out
            run_row.cost_usd = ctx.llm.cost_usd
            session.commit()

            ctx.emit("info", "design_resumed", step="designer",
                     status=run_row.status,
                     detail={"version": design_version + 1, "ok": bool(design_result.get("ok"))})
    except Exception as e:
        log.error(f"[RESUME ERROR] {e}")
        with SessionLocal() as session:
            run_row = session.get(Run, run_id)
            if run_row:
                run_row.status = "failed"
                run_row.error = str(e)
                session.commit()
        ctx.emit("error", "resume_run", step="designer", status="failed", detail={"error": str(e)})
    finally:
        ctx.close()


# --- Pose Regeneration ---

RUN_WAITING_STATUSES = {"awaiting_approval", "awaiting_assets"}


def _execute_regenerate_task(run_id: Optional[str], asset_id: int, pose: str,
                             person_id: str, prompt: str):
    """Generate kandidat pose baru (selalu pending_review); jika terkait run, lanjutkan run.

    Kegagalan generate tidak boleh membuat run stuck 'running': run dikembalikan ke
    'awaiting_assets' dengan pesan error supaya bisa dicoba lagi.
    """
    from src.carousel.tools import cloudflare_pose_generator

    ctx = None
    generated = False
    try:
        if run_id:
            with SessionLocal() as session:
                run_row = session.get(Run, run_id)
                topic = run_row.topic if run_row else ""
            ctx = create_run_context(topic, pipeline.load_brand(), run_id=run_id)
            ctx.emit("info", "pose_regenerate_started", step="designer",
                     detail={"replaces_asset_id": asset_id, "pose": pose, "person_id": person_id})
        staged = cloudflare_pose_generator.generate_pose(
            person_id, pose, prompt, force=True, ctx=ctx
        ) if ctx else cloudflare_pose_generator.generate_pose(person_id, pose, prompt, force=True)
        generated = True
        if ctx:
            ctx.emit("info", "pose_regenerate_finished", step="designer",
                     detail={"new_asset_id": staged.get("id"), "pose": pose,
                             "status": staged.get("status")})
    except Exception as e:
        log.error(f"[REGENERATE ERROR] asset {asset_id} pose {pose}: {e}")
        if run_id:
            try:
                with SessionLocal() as session:
                    run_row = session.get(Run, run_id)
                    if run_row:
                        run_row.status = "awaiting_assets"
                        run_row.error = f"Regenerate pose '{pose}' gagal: {e}"
                        session.commit()
            except Exception as db_exc:
                log.error(f"[REGENERATE ERROR] gagal mengembalikan status run {run_id}: {db_exc}")
        if ctx:
            ctx.emit("error", "pose_regenerate", step="designer", status="failed",
                     detail={"error": str(e), "error_type": type(e).__name__, "pose": pose})
    finally:
        if ctx:
            ctx.close()

    if generated and run_id:
        _execute_resume_task(run_id)


# --- Video Run Background Execution ---

def _output_url(path: Optional[str]) -> Optional[str]:
    """Ubah path lokal di bawah OUTPUT_DIR menjadi URL statis; None jika di luar/tidak ada."""
    if not path:
        return None
    try:
        p = Path(path).resolve()
        root = config.OUTPUT_DIR.resolve()
        if p.exists() and p.is_relative_to(root):
            return f"/static/output/{p.relative_to(root).as_posix()}"
    except (OSError, ValueError):
        pass
    return None


def _has_video_events(session, run_id: str) -> bool:
    """True jika run ini menjalankan pipeline video (event pertama sudah ber-step 'video')."""
    return session.scalar(
        select(func.count(Event.id)).where(Event.run_id == run_id, Event.step == "video")
    ) > 0


def _save_video_result(run_id: str, result_payload: dict, status: str, ctx=None,
                       error: Optional[str] = None) -> None:
    """Simpan hasil video sebagai Design row (plan_id kosong) dan finalisasi status Run.

    Hasil video disimpan di designs.result_json dengan type="video" sehingga tidak
    perlu migrasi skema, dan GET /runs/{id} bisa menampilkannya.
    """
    with SessionLocal() as session:
        version = session.scalar(
            select(func.max(Design.version)).where(Design.run_id == run_id)
        ) or 0
        session.add(Design(
            run_id=run_id,
            plan_id=None,
            version=version + 1,
            ok=bool(result_payload.get("ok")),
            result_json=json.dumps(result_payload, ensure_ascii=False),
            preview_path=None,
        ))
        run_row = session.get(Run, run_id)
        if run_row:
            run_row.status = status
            run_row.finished_at = datetime.now(timezone.utc)
            run_row.error = error
            if ctx is not None:
                run_row.tokens_in = ctx.llm.tokens_in
                run_row.tokens_out = ctx.llm.tokens_out
                run_row.cost_usd = ctx.llm.cost_usd
        session.commit()


def _execute_video_pipeline_task(run_id: str, topic: str, duration: int, fresh: bool = True):
    """Execute video pipeline; successful QC awaits human approval before publication."""
    import asyncio
    from src.reels.pipeline import VideoPipeline
    from src.video.research_cache import make_researcher

    brand = pipeline.load_brand()
    ctx = create_run_context(topic, brand, run_id=run_id)
    try:
        ctx.emit("info", "run_started", step="video", detail={"topic": topic, "format": "video"})
        out_path = config.OUTPUT_DIR / "reels" / f"reels_{run_id}.mp4"

        vp = VideoPipeline(context=ctx, researcher=make_researcher(ctx, fresh))
        result = asyncio.run(vp.run_pipeline(
            topic=topic,
            target_duration_sec=duration,
            out_video_path=str(out_path),
        ))

        payload = {
            "type": "video",
            "ok": bool(result.ok),
            "video_path": result.video_path,
            "duration_sec": result.duration_sec,
            "file_size_mb": result.file_size_mb,
            "scenes_count": result.scenes_count,
            "issues": list(result.issues),
        }
        status = "ok" if result.ok else "failed"
        if result.ok:
            status = "awaiting_approval"
        error = None if result.ok else "; ".join(result.issues) or "QC video gagal"
        _save_video_result(run_id, payload, status, ctx=ctx, error=error)
        ctx.emit("info", "run_finished", step="video", status=status,
                 tokens_in=ctx.llm.tokens_in, tokens_out=ctx.llm.tokens_out,
                 cost_usd=ctx.llm.cost_usd)
    except Exception as e:
        log.error(f"[API ERROR] Video pipeline execution failed for run {run_id}: {e}")
        try:
            _save_video_result(
                run_id,
                {"type": "video", "ok": False, "video_path": None, "issues": [str(e)]},
                "failed", ctx=ctx, error=f"{type(e).__name__}: {e}",
            )
        except Exception as db_exc:  # jangan sampai kegagalan DB menyembunyikan error asli
            log.error(f"[API ERROR] Gagal menyimpan status failed untuk run {run_id}: {db_exc}")
        ctx.emit("error", "video_pipeline", step="video", status="failed",
                 detail={"error": str(e), "error_type": type(e).__name__})
    finally:
        ctx.close()


# --- Endpoints ---

@app.get("/")
def health_check():
    return {
        "status": "online",
        "service": "GTNIC Social Media AI Agent API",
        "version": "1.0.0",
        "docs_url": "/docs"
    }


@app.get("/api/v1/brand")
def get_brand_profile():
    """Mengambil konfigurasi brand, tema warna, dan fakta terverifikasi."""
    try:
        brand_data = pipeline.load_brand()
        logo_path = config.ROOT / "assets" / "logo.png"
        ref_path = config.ROOT / "data" / "people" / "operator_01" / "reference.png"
        brand_data["has_logo"] = logo_path.exists()
        brand_data["logo_url"] = "/static/assets/logo.png" if logo_path.exists() else None
        brand_data["has_talent_ref"] = ref_path.exists()
        brand_data["talent_ref_url"] = "/static/data/people/operator_01/reference.png" if ref_path.exists() else None
        return brand_data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/brand", dependencies=[Depends(auth.verify_api_key)])
def update_brand_profile(req: BrandUpdateRequest):
    """Memperbarui profil brand, nomor telepon, handle, dan tema warna di brand.json."""
    try:
        brand_file = config.ROOT / "config" / "brand.json"
        brand_data = json.loads(brand_file.read_text(encoding="utf-8")) if brand_file.exists() else {}

        if req.company is not None:
            brand_data["company"] = req.company
            brand_data.setdefault("chrome", {})["brand_text"] = req.company
        if req.industry is not None:
            brand_data["industry"] = req.industry
        if req.description is not None:
            brand_data["description"] = req.description
        if req.audience is not None:
            brand_data["audience"] = req.audience

        # Update phone & handle
        chrome = brand_data.setdefault("chrome", {})
        footer = chrome.setdefault("footer", {"show": True, "lines": []})
        current_lines = list(footer.get("lines") or ["", ""])
        while len(current_lines) < 2:
            current_lines.append("")

        if req.handle is not None:
            current_lines[0] = req.handle
        if req.phone is not None:
            current_lines[1] = req.phone
        footer["lines"] = current_lines

        # Update colors
        colors = brand_data.setdefault("colors", {})
        tokens = brand_data.setdefault("tokens", {})

        if req.primary_color:
            colors["primary"] = req.primary_color
            tokens["bg"] = req.primary_color
        if req.secondary_color:
            colors["secondary"] = req.secondary_color
            tokens["light_bg"] = req.secondary_color
        if req.accent_color:
            colors["accent"] = req.accent_color
            tokens["accent"] = req.accent_color

        brand_file.write_text(json.dumps(brand_data, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"status": "ok", "message": "Brand profile berhasil diperbarui", "brand": brand_data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _validate_image_file(file: UploadFile, max_mb: float = 10.0, allowed_formats=('PNG', 'JPEG', 'WEBP')) -> bytes:
    """Read an image in bounded chunks and verify its decoded format."""
    import io
    from PIL import Image

    max_bytes = int(max_mb * 1024 * 1024)
    chunks = []
    total = 0
    while True:
        chunk = file.file.read(min(64 * 1024, max_bytes - total + 1))
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=400, detail=f"Ukuran file melebihi batas maksimum {max_mb:.0f} MB")
        chunks.append(chunk)
    contents = b"".join(chunks)
    if total > max_bytes:
        raise HTTPException(status_code=400, detail=f"Ukuran file melebihi batas maksimum {max_mb:.0f} MB")
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="File kosong tidak dapat diupload")
    try:
        im = Image.open(io.BytesIO(contents))
        fmt = (im.format or "").upper()
        if fmt not in allowed_formats:
            raise HTTPException(status_code=400, detail=f"Format gambar '{fmt}' tidak didukung; gunakan {allowed_formats}")
        if im.width * im.height > 40_000_000:
            raise HTTPException(status_code=400, detail="Resolusi gambar melebihi batas aman (40 megapiksel)")
        im.load()
        im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
        normalized = io.BytesIO()
        im.save(normalized, format="PNG", optimize=True)
        contents = normalized.getvalue()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"File gambar tidak valid atau rusak: {e}")
    return contents


@app.post("/api/v1/brand/logo", dependencies=[Depends(auth.verify_api_key)])
def upload_brand_logo(file: UploadFile = File(...)):
    """Upload logo brand dan simpan ke assets/logo.png."""
    logo_path: Path | None = None
    try:
        contents = _validate_image_file(file, max_mb=5.0)
        assets_dir = config.ROOT / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        logo_path = assets_dir / "logo.png"
        logo_path.write_bytes(contents)

        # Update brand.json logo_path
        brand_file = config.ROOT / "config" / "brand.json"
        if brand_file.exists():
            brand_data = json.loads(brand_file.read_text(encoding="utf-8"))
            brand_data["logo_path"] = "assets/logo.png"
            brand_file.write_text(json.dumps(brand_data, indent=2, ensure_ascii=False), encoding="utf-8")

        return {"status": "ok", "message": "Logo berhasil disimpan", "path": "assets/logo.png"}
    except HTTPException:
        raise
    except Exception as e:
        if logo_path is not None:
            try:
                logo_path.unlink(missing_ok=True)
            except OSError as cleanup_error:
                log.error(f"[UPLOAD] Failed to clean temporary logo: {cleanup_error}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/layouts")
def list_layouts(role: Optional[str] = None, approved_only: bool = True):
    """Daftar layout template yang tersedia di sistem."""
    statuses = ("approved",) if approved_only else ("approved", "draft", "retired")
    items = registry.catalog(statuses=statuses)
    if role:
        items = [i for i in items if i.get("role") == role]
    return {
        "total": len(items),
        "layouts": items
    }


@app.post("/api/v1/runs/generate", dependencies=[Depends(auth.verify_api_key)])
def create_run(req: TriggerRunRequest, background_tasks: BackgroundTasks):
    """Memicu pembuatan konten carousel secara otonom oleh AI Agent."""
    brand = pipeline.load_brand()
    # Buat context run lebih awal untuk mencatat status 'running' di database
    ctx = create_run_context(req.topic, brand)
    run_id = ctx.run_id
    ctx.close()

    # Eksekusi pipeline di background agar HTTP request langsung merespon ID run
    background_tasks.add_task(_execute_pipeline_task, run_id, req.topic, req.fresh, req.include_design)

    return {
        "run_id": run_id,
        "status": "running",
        "topic": req.topic,
        "message": "AI Agent sedang memproses riset, perencanaan slide, dan rendering."
    }


@app.get("/api/v1/runs")
def list_runs(limit: int = 30, offset: int = 0, status: Optional[str] = None):
    """Riwayat run (terbaru dulu) untuk panel history dan daftar yang menunggu approval.

    Query: `limit` (1-100), `offset`, `status` (mis. awaiting_approval, ok, failed, running).
    Tiap item memuat `format` (carousel|video), `pending_review_count` (pose yang
    masih menunggu keputusan *saat ini*), serta `thumbnail_url` / `video_url`.
    """
    from src.carousel.tools import asset_library

    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    with SessionLocal() as session:
        base = select(Run)
        count_q = select(func.count(Run.id))
        if status:
            base = base.where(Run.status == status)
            count_q = count_q.where(Run.status == status)
        total = session.scalar(count_q) or 0
        rows = session.scalars(
            base.order_by(desc(Run.started_at)).limit(limit).offset(offset)
        ).all()
        run_ids = [r.id for r in rows]

        latest_design: dict[str, dict] = {}
        video_run_ids: set[str] = set()
        if run_ids:
            for d in session.scalars(
                select(Design).where(Design.run_id.in_(run_ids)).order_by(Design.version.asc())
            ):
                try:
                    latest_design[d.run_id] = json.loads(d.result_json or "{}")
                except ValueError:
                    latest_design[d.run_id] = {}
            video_run_ids = set(session.scalars(
                select(Event.run_id).where(Event.run_id.in_(run_ids), Event.step == "video").distinct()
            ))

    still_pending_ids = {a["id"] for a in asset_library.pending_assets()}

    items = []
    for r in rows:
        dd = latest_design.get(r.id) or {}
        is_video = dd.get("type") == "video" or r.id in video_run_ids
        pending_count = 0
        thumb = None
        video_url = None
        if is_video:
            video_url = _output_url(dd.get("video_path"))
        else:
            pending_count = sum(1 for pr in dd.get("pending_review") or [] if pr.get("id") in still_pending_ids)
            for sl in dd.get("slides") or []:
                thumb = _output_url(sl.get("path"))
                if thumb:
                    break
        items.append({
            "run_id": r.id,
            "topic": r.topic,
            "status": r.status,
            "format": "video" if is_video else "carousel",
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "cost_usd": r.cost_usd or 0.0,
            "error": r.error,
            "pending_review_count": pending_count,
            "thumbnail_url": thumb,
            "video_url": video_url,
        })

    return {"total": total, "limit": limit, "offset": offset, "runs": items}


@app.get("/api/v1/runs/{run_id}")
def get_run_status(run_id: str):
    """Mengecek status proses run, data riset, plan, dan hasil gambar desain."""
    with SessionLocal() as session:
        run_row = session.get(Run, run_id)
        if not run_row:
            raise HTTPException(status_code=404, detail="Run tidak ditemukan")

        # Ambil plan terbaru
        plan_row = session.scalars(
            select(Plan).where(Plan.run_id == run_id).order_by(desc(Plan.version))
        ).first()

        # Ambil design terbaru
        design_row = session.scalars(
            select(Design).where(Design.run_id == run_id).order_by(desc(Design.version))
        ).first()

        plan_data = json.loads(plan_row.plan_json) if plan_row and plan_row.plan_json else None
        design_data = json.loads(design_row.result_json) if design_row and design_row.result_json else None

        # Run video menyimpan hasilnya di designs.result_json dengan type="video"
        is_video = bool(design_data and design_data.get("type") == "video")
        video_preview = None
        if is_video:
            vpath = design_data.get("video_path")
            video_preview = {
                "ok": bool(design_data.get("ok")),
                "url": _output_url(vpath),
                "duration_sec": design_data.get("duration_sec", 0.0),
                "file_size_mb": design_data.get("file_size_mb", 0.0),
                "scenes_count": design_data.get("scenes_count", 0),
                "issues": design_data.get("issues", []),
            }
            try:
                from src.agents import publisher as _pub
                video_preview["suggested_caption"] = _pub.default_video_caption(run_row.topic, pipeline.load_brand())
            except Exception:  # noqa: BLE001 - saran caption bersifat opsional
                video_preview["suggested_caption"] = run_row.topic

        pub_row = session.scalars(
            select(Publication).where(Publication.run_id == run_id).order_by(desc(Publication.id))
        ).first()
        publication = {
            "status": pub_row.status, "media_id": pub_row.media_id,
            "permalink": pub_row.permalink, "error": pub_row.error,
        } if pub_row else None

        # Ubah path lokal slides menjadi URL statis yang bisa langsung ditampilkan browser frontend
        slides_preview = []
        if design_data and "slides" in design_data:
            for s in design_data["slides"]:
                local_path = s.get("path")
                if local_path:
                    # Ambil relative path terhadap output/
                    rel_path = Path(local_path).relative_to(config.OUTPUT_DIR) if str(config.OUTPUT_DIR) in str(local_path) else Path(local_path).name
                    s_copy = dict(s)
                    s_copy["image_url"] = f"/static/output/{Path(rel_path).as_posix()}?v={design_row.id}"
                    slides_preview.append(s_copy)

        # Eksekusi pending_review format url
        pending_review_preview = []
        if design_data and "pending_review" in design_data:
            for pr in design_data["pending_review"]:
                pr_copy = dict(pr)
                # Status terkini dari library (snapshot di design bisa sudah usang
                # kalau aset sudah di-approve/reject setelah design dibuat)
                try:
                    from src.carousel.tools import asset_library as _al
                    live = _al.get_asset(pr.get("id")) if pr.get("id") is not None else None
                    pr_copy["status"] = live["status"] if live else "missing"
                except Exception:
                    pr_copy["status"] = "unknown"
                pr_p = pr.get("path")
                if pr_p:
                    pr_obj = Path(pr_p).resolve()
                    if pr_obj.exists() and pr_obj.is_relative_to((config.ROOT / "data").resolve()):
                        rel = pr_obj.relative_to((config.ROOT / "data").resolve())
                        pr_copy["url"] = f"/static/data/{rel}"
                    elif pr_obj.exists() and pr_obj.is_relative_to(config.OUTPUT_DIR.resolve()):
                        rel = pr_obj.relative_to(config.OUTPUT_DIR.resolve())
                        pr_copy["url"] = f"/static/output/{rel}"
                pending_review_preview.append(pr_copy)

        return {
            "run_id": run_row.id,
            "topic": run_row.topic,
            "format": "video" if is_video or _has_video_events(session, run_id) else "carousel",
            "status": run_row.status,
            "started_at": run_row.started_at.isoformat() if run_row.started_at else None,
            "finished_at": run_row.finished_at.isoformat() if run_row.finished_at else None,
            "tokens_in": run_row.tokens_in or 0,
            "tokens_out": run_row.tokens_out or 0,
            "cost_usd": run_row.cost_usd or 0.0,
            "error": run_row.error,
            "plan": plan_data,
            "video": video_preview,
            "publication": publication,
            "design": {
                "ok": design_row.ok if design_row else False,
                "slides": slides_preview,
                "pending_review": pending_review_preview,
                "missing_poses": design_data.get("missing_poses", []) if design_data else [],
                "preview_path": (f"{_output_url(design_row.preview_path)}?v={design_row.id}" if _output_url(design_row.preview_path) else None) if design_row and design_row.preview_path else None
            } if design_row and not is_video else None
        }


@app.get("/api/v1/runs/{run_id}/events")
def get_run_events(run_id: str):
    """Mengambil riwayat thought process, log agent, dan audit trail untuk panel UI."""
    with SessionLocal() as session:
        events = session.scalars(
            select(Event).where(Event.run_id == run_id).order_by(Event.ts.asc())
        ).all()

        return {
            "run_id": run_id,
            "total_events": len(events),
            "events": [
                {
                    "id": e.id,
                    "timestamp": e.ts.isoformat() if e.ts else None,
                    "step": e.step,
                    "kind": e.kind,
                    "name": e.name,
                    "status": e.status,
                    "cost_usd": e.cost_usd,
                    "duration_ms": e.duration_ms,
                    "detail": json.loads(e.detail_json) if e.detail_json else None
                }
                for e in events
            ]
        }


def _publish_video_run(run_row: Run, video: dict, req: Optional[PublishOptions], brand: dict) -> dict:
    """Posting Reels: preflight -> upload MP4 -> Instagram. Caption final datang dari UI (diedit manusia)."""
    from src.agents import publisher

    caption = ((req.caption if req else None) or publisher.default_video_caption(run_row.topic, brand)).strip()
    share_to_feed = req.share_to_feed if req else True

    ctx = create_run_context(run_row.topic, brand, run_id=run_row.id)
    try:
        problems = publisher.preflight_video(video, caption, run_id=run_row.id, session=ctx.session, ctx=ctx)
        if problems:
            raise HTTPException(status_code=400, detail="; ".join(problems))
        with SessionLocal() as db_session:
            cal_item = db_session.scalars(select(ContentStrategyItem).where(
                ContentStrategyItem.run_id == run_row.id
            )).first()
            if not cal_item or cal_item.status not in {"approved", "approved_to_publish", "scheduled"}:
                raise HTTPException(status_code=409, detail="Item kalender belum disetujui untuk publikasi.")
            prior_publication = db_session.scalars(select(Publication).where(
                Publication.run_id == run_row.id, Publication.status.in_(["intent", "published"])
            )).first()
            if prior_publication:
                raise HTTPException(status_code=409, detail="Run ini sudah memiliki publication berjalan atau berhasil.")
            cal_item.status = "publishing"
            db_session.commit()
        result = publisher.publish_reel(video["video_path"], caption, share_to_feed=share_to_feed, ctx=ctx)
        is_ok = bool(result.get("media_id"))

        # Record tracking against the persisted publication; NULL means metrics have not been ingested.
        if is_ok:
            with SessionLocal() as db_session:
                publication = db_session.scalars(select(Publication).where(
                    Publication.run_id == run_row.id, Publication.status == "published"
                ).order_by(desc(Publication.id))).first()
                cal_item = db_session.scalars(select(ContentStrategyItem).where(ContentStrategyItem.run_id == run_row.id)).first()
                if cal_item:
                    cal_item.status = "published"
                if publication:
                    analytics = db_session.scalars(select(PostAnalytics).where(
                        PostAnalytics.publication_id == publication.id
                    )).first()
                    if analytics is None:
                        analytics = PostAnalytics(
                            publication_id=publication.id,
                            run_id=run_row.id,
                            strategy_item_id=cal_item.id if cal_item else None,
                            media_id=publication.media_id,
                            permalink=publication.permalink,
                            topic=run_row.topic,
                            format="video",
                            content_pillar=cal_item.content_pillar if cal_item else "Belum diklasifikasikan",
                            source="instagram_api_pending_metrics",
                            is_simulated=False,
                        )
                        db_session.add(analytics)
                db_session.commit()
        else:
            with SessionLocal() as db_session:
                cal_item = db_session.scalars(select(ContentStrategyItem).where(
                    ContentStrategyItem.run_id == run_row.id
                )).first()
                if cal_item:
                    cal_item.status = "publication_failed"
                    cal_item.approval_notes = str(result.get("error") or "Publisher returned no media identifier")[:500]
                    db_session.commit()

        return {
            "run_id": run_row.id,
            "format": "reel",
            "status": "published" if is_ok else "failed",
            "media_id": result.get("media_id"),
            "permalink": result.get("permalink"),
            "error": result.get("error"),
        }
    except HTTPException:
        raise
    except Exception as e:
        try:
            with SessionLocal() as db_session:
                cal_item = db_session.scalars(select(ContentStrategyItem).where(
                    ContentStrategyItem.run_id == run_row.id
                )).first()
                if cal_item and cal_item.status == "publishing":
                    cal_item.status = "publication_failed"
                    cal_item.approval_notes = f"Publication gagal: {e}"[:500]
                    db_session.commit()
        except Exception as status_exc:
            log.error(f"[PUBLISH REEL] Failed to record publication failure state: {status_exc}")
        log.error(f"[PUBLISH REEL ERROR] {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")
    finally:
        ctx.close()


@app.post("/api/v1/runs/{run_id}/publish", dependencies=[Depends(auth.verify_api_key)])
def publish_run_to_instagram(run_id: str, req: Optional[PublishOptions] = None):
    """Mempublikasikan hasil run ke Instagram: carousel (feed) atau Reels (video)."""
    from src.agents import publisher

    brand = pipeline.load_brand()
    with SessionLocal() as session:
        run_row = session.get(Run, run_id)
        if not run_row:
            raise HTTPException(status_code=404, detail="Run tidak ditemukan")
        if run_row.status in {"qc_failed", "failed", "generation_failed"}:
            raise HTTPException(status_code=409, detail=f"Run tidak dapat dipublikasikan dalam status '{run_row.status}'.")
        cal_item = session.scalars(select(ContentStrategyItem).where(
            ContentStrategyItem.run_id == run_id
        )).first()
        if not cal_item:
            raise HTTPException(status_code=409, detail="Run tidak memiliki item kalender yang disetujui untuk publikasi.")
        if cal_item.status not in {"approved", "approved_to_publish", "scheduled"}:
            raise HTTPException(status_code=409, detail="Item kalender belum disetujui untuk publikasi.")
        prior_publication = session.scalars(select(Publication).where(
            Publication.run_id == run_id, Publication.status.in_(["intent", "published"])
        )).first()
        if prior_publication:
            raise HTTPException(status_code=409, detail="Run ini sudah memiliki publication berjalan atau berhasil.")

        plan_row = session.scalars(
            select(Plan).where(Plan.run_id == run_id).order_by(desc(Plan.version))
        ).first()
        design_row = session.scalars(
            select(Design).where(Design.run_id == run_id).order_by(desc(Design.version))
        ).first()

        video_payload = None
        if design_row:
            maybe_video = json.loads(design_row.result_json or "{}")
            if maybe_video.get("type") == "video":
                video_payload = maybe_video
                if not video_payload.get("ok"):
                    raise HTTPException(status_code=409, detail="QC video gagal; publikasi diblokir.")
        if video_payload is None:
            if not plan_row or not design_row:
                raise HTTPException(status_code=400, detail="Plan atau Desain untuk run ini belum siap.")
            plan_data = json.loads(plan_row.plan_json)
            design_data = json.loads(design_row.result_json)
            semantic_qc = design_data.get("semantic_qc") or {}
            if semantic_qc and not semantic_qc.get("ok"):
                raise HTTPException(status_code=409, detail="Semantic QC gagal; publikasi diblokir.")
            if not design_row.ok:
                raise HTTPException(status_code=409, detail="QC/render desain gagal; publikasi diblokir.")

    # Reels diproses SETELAH sesi baca ditutup: upload + pemrosesan video memakan menit, dan transaksi baca
    # yang masih terbuka bisa memicu "database is locked" di SQLite saat publisher menulis baris intent.
    if video_payload is not None:
        return _publish_video_run(run_row, video_payload, req, brand)

    # Eksekusi publishing via publisher agent
    ctx = create_run_context(run_row.topic, brand, run_id=run_id)
    try:
        # Panggil preflight sebelum publish
        problems = publisher.preflight(plan_data, design_data, session=ctx.session, ctx=ctx)
        if problems:
            raise HTTPException(status_code=400, detail="; ".join(problems))

        with SessionLocal() as db_session:
            cal_item = db_session.scalars(select(ContentStrategyItem).where(
                ContentStrategyItem.run_id == run_id
            )).first()
            if cal_item:
                cal_item.status = "publishing"
                db_session.commit()

        slide_paths = [s["path"] for s in design_data.get("slides", [])]
        result = publisher.publish(plan_data, slide_paths, ctx=ctx)
        is_ok = bool(result.get("ok")) or bool(result.get("media_id"))

        # Record tracking against the persisted publication; NULL means metrics have not been ingested.
        if is_ok:
            with SessionLocal() as db_session:
                publication = db_session.scalars(select(Publication).where(
                    Publication.run_id == run_id, Publication.status == "published"
                ).order_by(desc(Publication.id))).first()
                cal_item = db_session.scalars(select(ContentStrategyItem).where(ContentStrategyItem.run_id == run_id)).first()
                if cal_item:
                    cal_item.status = "published"
                if publication:
                    analytics = db_session.scalars(select(PostAnalytics).where(
                        PostAnalytics.publication_id == publication.id
                    )).first()
                    if analytics is None:
                        db_session.add(PostAnalytics(
                            publication_id=publication.id,
                            run_id=run_id,
                            strategy_item_id=cal_item.id if cal_item else None,
                            media_id=publication.media_id,
                            permalink=publication.permalink,
                            topic=run_row.topic,
                            format="carousel",
                            content_pillar=cal_item.content_pillar if cal_item else plan_data.get("content_pillar", "Belum diklasifikasikan"),
                            source="instagram_api_pending_metrics",
                            is_simulated=False,
                        ))
                elif not is_ok and cal_item:
                    cal_item.status = "publication_failed"
                    cal_item.approval_notes = str(result.get("error") or "Publisher returned no media identifier")[:500]
                db_session.commit()

        return {
            "run_id": run_id,
            "status": "published" if is_ok else "failed",
            "media_id": result.get("media_id"),
            "permalink": result.get("permalink"),
            "error": result.get("error")
        }
    except HTTPException:
        raise
    except Exception as e:
        try:
            with SessionLocal() as db_session:
                cal_item = db_session.scalars(select(ContentStrategyItem).where(
                    ContentStrategyItem.run_id == run_id
                )).first()
                if cal_item and cal_item.status == "publishing":
                    cal_item.status = "publication_failed"
                    cal_item.approval_notes = f"Publication gagal: {e}"[:500]
                    db_session.commit()
        except Exception as status_exc:
            log.error(f"[PUBLISH] Failed to record publication failure state: {status_exc}")
        log.error(f"[PUBLISH ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        ctx.close()


class AssetPermissions(BaseModel):
    source_type: Optional[str] = None      # uploaded | ai_generated | stock | brand_owned
    license_note: Optional[str] = None
    allowed_uses: Optional[List[str]] = None  # social_post, video, ads, website, internal


@app.post("/api/v1/assets/{asset_id}/permissions", dependencies=[Depends(auth.verify_api_key)])
def set_asset_permissions(asset_id: int, req: AssetPermissions):
    """Atur sumber, catatan lisensi, dan tujuan penggunaan yang diizinkan untuk sebuah aset."""
    from src.carousel.tools import asset_library
    try:
        n = asset_library.set_permissions(asset_id, source_type=req.source_type, license_note=req.license_note,
                                          allowed_uses=req.allowed_uses)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not n:
        raise HTTPException(status_code=404, detail="Asset tidak ditemukan")
    return asset_library.get_asset(asset_id)


@app.post("/api/v1/assets/{asset_id}/review", dependencies=[Depends(auth.verify_api_key)])
def review_pending_asset(asset_id: int, status: str = "approved"):
    """Menyetujui (approve) atau menolak (reject) pose hasil generate Cloudflare."""
    from src.carousel.tools import asset_library, cloudflare_pose_generator
    if status not in {"approved", "rejected"}:
        raise HTTPException(status_code=400, detail="Status harus 'approved' atau 'rejected'")

    try:
        asset = asset_library.get_asset(asset_id)
        if not asset:
            raise HTTPException(status_code=404, detail="Asset tidak ditemukan")

        if status == "approved":
            qc = cloudflare_pose_generator.quality_check_generated(asset["path"])
            if not qc.get("ok"):
                raise HTTPException(status_code=400, detail=f"Asset gagal QC: {qc.get('issues')}")

        resolved_id = asset_library.set_status(asset_id, status)
        return {
            "status": "ok",
            "asset_id": resolved_id,
            "decision": status,
            "message": f"Asset ID {resolved_id} berhasil di-{status}."
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/runs/{run_id}/resume", dependencies=[Depends(auth.verify_api_key)])
def resume_run_endpoint(run_id: str, background_tasks: BackgroundTasks):
    """Melanjutkan rendering run yang sebelumnya berstatus awaiting_approval setelah aset disetujui."""
    with SessionLocal() as session:
        run_row = session.get(Run, run_id)
        if not run_row:
            raise HTTPException(status_code=404, detail="Run tidak ditemukan")
        if run_row.status not in {"awaiting_approval", "awaiting_assets", "ok", "failed"}:
            raise HTTPException(status_code=400, detail=f"Run berstatus {run_row.status}, tidak bisa di-resume.")

        run_row.status = "running"
        session.commit()

    background_tasks.add_task(_execute_resume_task, run_id)
    return {
        "run_id": run_id,
        "status": "running",
        "message": "AI Designer sedang melanjutkan perakitan slide dengan aset yang telah diapprove."
    }


@app.post("/api/v1/assets/{asset_id}/regenerate", dependencies=[Depends(auth.verify_api_key)])
def regenerate_pose_endpoint(asset_id: int, req: RegeneratePoseRequest,
                             background_tasks: BackgroundTasks):
    """Buat ulang pose yang ditolak (kandidat baru, tetap perlu review manusia).

    - Jika run terkait sedang menunggu (awaiting_approval/awaiting_assets): kandidat baru dibuat
      lalu run dilanjutkan otomatis sehingga kembali ke 'awaiting_approval'.
    - Jika tidak ada run yang menunggu: hanya membuat kandidat baru di Asset Library.
    Proses berjalan di background (generate gambar + hapus background bisa >1 menit).
    """
    from src.carousel.tools import asset_library, cloudflare_pose_generator

    asset = asset_library.get_asset(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset tidak ditemukan")
    if asset.get("status") != "rejected":
        raise HTTPException(
            status_code=400,
            detail=f"Hanya pose berstatus 'rejected' yang bisa dibuat ulang (saat ini: {asset.get('status')}).",
        )

    pose = next((t for t in (asset.get("tags") or []) if t), "")
    person_id = asset.get("person_id") or ""
    if not pose or not person_id or not asset.get("model"):  # hanya hasil generate yang punya model
        raise HTTPException(status_code=400, detail="Asset ini bukan pose hasil generate, tidak bisa dibuat ulang.")
    if pose not in cloudflare_pose_generator.POSE_GUIDANCE and not req.prompt.strip():
        raise HTTPException(status_code=400, detail=f"Pose '{pose}' belum punya arahan bawaan; isi 'prompt'.")
    try:
        has_reference = bool(asset_library.get_person_reference(person_id))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not has_reference:
        raise HTTPException(status_code=400, detail=f"Foto referensi untuk '{person_id}' belum diupload.")
    if not (config.opt("CLOUDFLARE_ACCOUNT_ID") and config.opt("CLOUDFLARE_API_TOKEN")):
        raise HTTPException(status_code=400, detail="CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN belum diisi di .env")

    run_id = req.run_id or asset.get("run_id")
    mode = "standalone"
    with SessionLocal() as session:
        run_row = session.get(Run, run_id) if run_id else None
        if req.run_id and not run_row:
            raise HTTPException(status_code=404, detail="Run tidak ditemukan")
        if run_row and run_row.status == "running":
            raise HTTPException(status_code=409, detail="Run sedang diproses; tunggu sampai selesai.")
        if run_row and run_row.status in RUN_WAITING_STATUSES:
            run_row.status = "running"
            run_row.error = None
            session.commit()
            mode = "run"
    linked_run = run_id if mode == "run" else None

    background_tasks.add_task(_execute_regenerate_task, linked_run, asset_id, pose, person_id, req.prompt)
    return {
        "status": "running",
        "mode": mode,
        "asset_id": asset_id,
        "run_id": linked_run,
        "message": (
            "Membuat kandidat pose baru, lalu run dilanjutkan otomatis."
            if mode == "run" else
            "Membuat kandidat pose baru di Asset Library (tidak ada run yang menunggu)."
        ),
    }


@app.post("/api/v1/assets/upload", dependencies=[Depends(auth.verify_api_key)])
def upload_talent_reference(
    file: UploadFile = File(...),
    person_id: str = Form("operator_01"),
    description: str = Form("Foto mentah orang tanpa pose sebagai referensi AI"),
    source_type: str = Form("uploaded"),
    license_note: str = Form(""),
    allowed_uses: str = Form("social_post"),
):
    """Upload mentahan foto orang tanpa pose untuk referensi Cloudflare Workers AI."""
    from src.carousel.tools.asset_library import add_asset
    dest_path: Path | None = None
    try:
        import re
        if not re.match(r'^[a-zA-Z0-9_-]{1,64}$', person_id):
            raise HTTPException(status_code=400, detail="person_id hanya boleh alfanumerik, underscore, atau tanda hubung (-)")
        contents = _validate_image_file(file, max_mb=10.0)
        people_dir = config.ROOT / "data" / "people" / person_id
        people_dir.mkdir(parents=True, exist_ok=True)
        dest_path = people_dir / "reference.png"
        dest_path.write_bytes(contents)

        # Daftarkan juga ke asset_library agar langsung muncul di Asset Library UI
        asset_id = add_asset(
            path=str(dest_path),
            tags=["mentahan", "reference", person_id],
            description=description,
            status="approved",
            person_id=person_id,
            kind="reference",
            source_type=source_type[:32], license_note=license_note[:300],
            allowed_uses=[u for u in allowed_uses.split(",") if u.strip()],
        )

        return {
            "status": "ok",
            "message": f"Foto referensi mentah untuk person '{person_id}' berhasil diupload",
            "path": str(dest_path),
            "asset_id": asset_id,
            "person_id": person_id
        }
    except HTTPException:
        raise
    except Exception as e:
        if dest_path is not None:
            try:
                dest_path.unlink(missing_ok=True)
                if dest_path.parent.exists() and not any(dest_path.parent.iterdir()):
                    dest_path.parent.rmdir()
            except OSError as cleanup_error:
                log.error(f"[UPLOAD] Failed to clean temporary reference file: {cleanup_error}")
        raise HTTPException(status_code=500, detail=str(e))


ASSET_STATUSES = {"pending_review", "approved", "rejected", "placeholder"}
ASSET_STATUS_ALIASES = {"pending": "pending_review"}


def _static_url_for(p: str) -> Optional[str]:
    """Path lokal aset -> URL statis (output/, data/, assets/) atau None."""
    if not p:
        return None
    p_obj = Path(p).resolve()
    if not p_obj.exists():
        return None
    for base, prefix in (
        (config.OUTPUT_DIR, "output"),
        (config.ROOT / "data", "data"),
        (config.ROOT / "assets", "assets"),
    ):
        base = base.resolve()
        if p_obj.is_relative_to(base):
            return f"/static/{prefix}/{p_obj.relative_to(base).as_posix()}"
    return None


@app.get("/api/v1/assets")
def list_system_assets(status: Optional[str] = None):
    """Daftar asset talent / cutouts.

    Query `status` (opsional): pending | pending_review | approved | rejected | placeholder | all.
    `pending` adalah alias dari `pending_review` (nama status di database).
    Respons selalu menyertakan `counts` per status (tidak terpengaruh filter) untuk badge UI.
    """
    from collections import Counter
    from src.carousel.tools.asset_library import list_assets

    wanted = None
    if status and status != "all":
        wanted = ASSET_STATUS_ALIASES.get(status, status)
        if wanted not in ASSET_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"status tidak valid: '{status}'. Gunakan salah satu dari "
                       f"pending, {', '.join(sorted(ASSET_STATUSES))}, all.",
            )
    try:
        raw_assets = list_assets()
        counts = Counter(a.get("status", "approved") for a in raw_assets)
        if wanted:
            raw_assets = [a for a in raw_assets if a.get("status") == wanted]
        formatted = []
        for a in raw_assets:
            p = a.get("path", "")
            formatted.append({
                "id": a.get("id"),
                "tags": a.get("tags", []),
                "description": a.get("description", ""),
                "status": a.get("status", "approved"),
                "path": p,
                "url": _static_url_for(p),
                "run_id": a.get("run_id"),
                "person_id": a.get("person_id"),
                "kind": a.get("kind"),
                "created_at": str(a.get("created_at", ""))
            })
        # Terbaru di atas supaya aset yang baru perlu di-review mudah ditemukan
        formatted.sort(key=lambda x: x["id"] or 0, reverse=True)
        return {
            "total": len(formatted),
            "counts": {k: counts.get(k, 0) for k in sorted(ASSET_STATUSES)} | {"all": sum(counts.values())},
            "assets": formatted
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/runs/generate-video", dependencies=[Depends(auth.verify_api_key)])
def create_video_run(req: VideoRunRequest, background_tasks: BackgroundTasks):
    """Memicu pipeline pembuatan short-form video vertikal (Script -> TTS -> B-Roll -> Assembly -> QC)."""
    brand = pipeline.load_brand()
    ctx = create_run_context(req.topic, brand)
    run_id = ctx.run_id
    ctx.close()

    background_tasks.add_task(_execute_video_pipeline_task, run_id, req.topic, req.target_duration, req.fresh)

    return {
        "run_id": run_id,
        "status": "running",
        "topic": req.topic,
        "message": "AI Agent sedang memproses naskah, voiceover TTS, B-roll, dan compositing video."
    }

# ===========================================================================
# ENTERPRISE PROFILE & ONBOARDING (FEATURE-01)
# ===========================================================================

class EnterpriseProfileUpdate(BaseModel):
    company_name: str
    industry: str
    description: str
    products_services: List[Dict[str, Any]] = Field(default_factory=list)
    target_audience: Dict[str, Any] = Field(default_factory=dict)
    business_goals: List[str] = Field(default_factory=list)
    tone: str = "profesional, terpercaya"
    content_pillars: List[str] = Field(default_factory=list)
    brand_rules: List[str] = Field(default_factory=list)
    contact_info: Dict[str, Any] = Field(default_factory=dict)
    approval_workflow: Dict[str, Any] = Field(default_factory=dict)
    operating_preferences: Dict[str, Any] = Field(default_factory=dict)


@app.get("/api/v1/enterprise/profile")
def get_enterprise_profile_endpoint():
    """Mengambil profil lengkap perusahaan untuk konteks operasional agent."""
    with SessionLocal() as session:
        prof = get_or_create_enterprise_profile(session)
        data = {
            "id": prof.id,
            "company_name": prof.company_name,
            "industry": prof.industry,
            "description": prof.description,
            "products_services": json.loads(prof.products_services_json or "[]"),
            "target_audience": json.loads(prof.target_audience_json or "{}"),
            "business_goals": json.loads(prof.business_goals_json or "[]"),
            "tone": prof.tone,
            "content_pillars": json.loads(prof.content_pillars_json or "[]"),
            "brand_rules": json.loads(prof.brand_rules_json or "[]"),
            "contact_info": json.loads(prof.contact_info_json or "{}"),
            "approval_workflow": json.loads(prof.approval_workflow_json or "{}"),
            "operating_preferences": json.loads(prof.operating_preferences_json or "{}"),
            "completeness_score": prof.completeness_score,
            "updated_at": prof.updated_at.isoformat() if prof.updated_at else None
        }
        return data


@app.put("/api/v1/enterprise/profile", dependencies=[Depends(auth.verify_api_key)])
def update_enterprise_profile_endpoint(req: EnterpriseProfileUpdate):
    """Memperbarui profil & batasan perusahaan tanpa edit file JSON manual."""
    with SessionLocal() as session:
        prof = get_or_create_enterprise_profile(session)
        prof.company_name = req.company_name.strip()
        prof.industry = req.industry.strip()
        prof.description = req.description.strip()
        prof.products_services_json = json.dumps(req.products_services, ensure_ascii=False)
        prof.target_audience_json = json.dumps(req.target_audience, ensure_ascii=False)
        prof.business_goals_json = json.dumps(req.business_goals, ensure_ascii=False)
        prof.tone = req.tone.strip()
        prof.content_pillars_json = json.dumps(req.content_pillars, ensure_ascii=False)
        prof.brand_rules_json = json.dumps(req.brand_rules, ensure_ascii=False)
        prof.contact_info_json = json.dumps(req.contact_info, ensure_ascii=False)
        prof.approval_workflow_json = json.dumps(req.approval_workflow, ensure_ascii=False)
        prof.operating_preferences_json = json.dumps(req.operating_preferences, ensure_ascii=False)

        score = calculate_profile_completeness(req.model_dump())
        prof.completeness_score = score
        prof.updated_at = datetime.now(timezone.utc)
        version = prof.updated_at.isoformat()
        session.add(EnterpriseProfileVersion(
            profile_id=prof.id,
            version=version,
            snapshot_json=json.dumps({**req.model_dump(), "id": prof.id, "version": version}, ensure_ascii=False),
        ))

        # Sinkronkan ringkasan dasar ke config/brand.json
        try:
            brand_file = config.ROOT / "config" / "brand.json"
            if brand_file.exists():
                bdata = json.loads(brand_file.read_text(encoding="utf-8"))
                bdata["company"] = prof.company_name
                bdata["industry"] = prof.industry
                bdata["description"] = prof.description
                bdata["tone"] = prof.tone
                bdata["content_pillars"] = req.content_pillars
                bdata["rules"] = req.brand_rules
                if req.target_audience.get("primary_segment"):
                    bdata["audience"] = req.target_audience["primary_segment"]
                brand_file.write_text(json.dumps(bdata, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

        session.commit()
        return {"status": "ok", "message": "Profil Enterprise berhasil diperbarui", "completeness_score": score}


# ===========================================================================
# STRATEGY & CONTENT CALENDAR (FEATURE-02)
# ===========================================================================

class StrategyItemAction(BaseModel):
    status: Optional[str] = None
    plan_date: Optional[str] = None
    scheduled_slot: Optional[str] = None
    approval_notes: Optional[str] = None


@app.get("/api/v1/strategy/calendar")
def get_strategy_calendar_endpoint(regenerate: bool = False):
    """Melihat kalender 7 hari. GET bersifat read-only; kalender dibuat otomatis hanya jika kosong.
    Parameter ``regenerate`` diabaikan di sini; gunakan POST /api/v1/strategy/calendar/regenerate."""
    with SessionLocal() as session:
        items = session.scalars(select(ContentStrategyItem).order_by(ContentStrategyItem.id.asc())).all()
        if not items:
            items = generate_7day_strategy(session, reset=False)
        return _calendar_payload(items)


@app.post("/api/v1/strategy/calendar/regenerate", dependencies=[Depends(auth.verify_api_key)])
def regenerate_strategy_calendar_endpoint():
    """Membuat ulang item draft/rejected kalender (terproteksi API key karena memakai kuota LLM)."""
    with SessionLocal() as session:
        items = generate_7day_strategy(session, reset=True)
        return _calendar_payload(items)


def _calendar_payload(items):
    if True:
        return {
            "total_items": len(items),
            "items": [
                {
                    "id": it.id,
                    "plan_date": it.plan_date,
                    "topic": it.topic,
                    "format": it.format,
                    "content_pillar": it.content_pillar,
                    "objective": it.objective,
                    "target_segment": it.target_segment,
                    "scheduled_slot": it.scheduled_slot,
                    "rationale": it.rationale,
                    "status": it.status,
                    "approval_notes": it.approval_notes,
                    "run_id": it.run_id,
                    "feedback_insight_id": it.feedback_insight_id,
                    "campaign_id": it.campaign_id,
                    "approved_by": it.approved_by,
                    "publish_attempts": it.publish_attempts or 0,
                    "next_attempt_at": it.next_attempt_at.isoformat() if it.next_attempt_at else None,
                    "last_error": it.last_error,
                    "is_published": it.status == "published",
                }
                for it in items
            ]
        }


@app.patch("/api/v1/strategy/calendar/{item_id}", dependencies=[Depends(auth.verify_api_key)])
def update_strategy_item_endpoint(item_id: int, req: StrategyItemAction):
    """Approve, reject, reschedule, atau edit item kalender konten."""
    with SessionLocal() as session:
        item = session.get(ContentStrategyItem, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item strategi tidak ditemukan")

        if req.status:
            if req.status not in CALENDAR_STATES:
                raise HTTPException(status_code=400, detail=f"Status tidak valid: {req.status}")
            if req.status != item.status and req.status not in CALENDAR_TRANSITIONS.get(item.status, set()):
                raise HTTPException(status_code=409,
                                    detail=f"Transisi status tidak diizinkan: {item.status} -> {req.status}")
            if req.status in {"approved", "approved_to_publish", "scheduled"} and item.run_id:
                linked_run = session.get(Run, item.run_id)
                if linked_run and linked_run.status in {"qc_failed", "failed", "generation_failed"}:
                    raise HTTPException(status_code=409, detail="Run gagal QC/generasi; approval diblokir.")
            item.status = req.status
            if req.status in {"approved", "approved_to_publish", "scheduled"}:
                item.approved_by = "api_user"  # persetujuan manusia (dipakai kebijakan autonomi)
            if req.status == "scheduled":
                item.publish_attempts, item.next_attempt_at, item.last_error = 0, None, None

        if req.plan_date:
            item.plan_date = req.plan_date
        if req.scheduled_slot:
            item.scheduled_slot = req.scheduled_slot
        if req.approval_notes is not None:
            item.approval_notes = req.approval_notes

        item.updated_at = datetime.now(timezone.utc)
        session.commit()
        return {"status": "ok", "item_id": item.id, "new_status": item.status}


@app.post("/api/v1/strategy/calendar/{item_id}/generate", dependencies=[Depends(auth.verify_api_key)])
def trigger_generation_from_strategy_item(item_id: int, background_tasks: BackgroundTasks, force: bool = False):
    """Memulai pipeline post otomatis langsung dari item strategi kalender yang telah disetujui."""
    with SessionLocal() as session:
        item = session.get(ContentStrategyItem, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item strategi tidak ditemukan")

        # P0.4: Approval enforcement gate
        if not force and item.status not in ("approved", "ready"):
            raise HTTPException(
                status_code=400,
                detail=f"Item strategi belum disetujui (status saat ini: '{item.status}'). Setujui (Approve) item terlebih dahulu sebelum digenerate."
            )
        if item.run_id:
            linked_run = session.get(Run, item.run_id)
            if linked_run and linked_run.status in {"qc_failed", "failed", "generation_failed"}:
                raise HTTPException(status_code=409, detail="Run sebelumnya gagal QC/generasi; buat run baru setelah memperbaiki konten.")

        gen_topic = item.topic
        if item.campaign_id:
            camp = session.get(Campaign, item.campaign_id)
            if camp and camp.status in {"active", "draft"}:
                gen_topic = f"{item.topic} (Kampanye: {camp.name}. Pesan utama: {camp.message}. Syarat konten: {camp.content_requirements})"[:900]
        brand = pipeline.load_brand()
        ctx = create_run_context(gen_topic, brand)
        run_id = ctx.run_id
        ctx.close()

        item.run_id = run_id
        item.status = "producing"
        session.commit()

        if item.format == "video":
            background_tasks.add_task(_execute_video_pipeline_task, run_id, gen_topic, 30, False)
        else:
            background_tasks.add_task(_execute_pipeline_task, run_id, gen_topic, False, True)

        return {"status": "producing", "run_id": run_id, "strategy_item_id": item.id}


# ===========================================================================
# ANALYTICS & CLOSED FEEDBACK LOOP (FEATURE-03)
# ===========================================================================

def _demo_seed_allowed() -> bool:
    """Seed demo hanya bila diizinkan eksplisit, atau default-nya di luar production."""
    flag = config.opt("ALLOW_DEMO_SEED", "").lower()
    if flag:
        return flag == "true"
    env = os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "development")).strip().lower()
    return env not in {"production", "prod"}


@app.post("/api/v1/analytics/seed-demo", dependencies=[Depends(auth.verify_api_key)])
def seed_demo_analytics_endpoint():
    """Mengisi dataset analytics DEMO (berlabel simulated) jika masih kosong."""
    with SessionLocal() as session:
        records = seed_demo_analytics_data(session)
        return {"status": "ok", "records": len(records), "is_simulated": True}


@app.post("/api/v1/analytics/ingest", dependencies=[Depends(auth.verify_api_key)])
def ingest_analytics_endpoint():
    """Tarik metrik Instagram asli untuk publikasi 'published' (30 hari terakhir) lalu hasilkan insight bila data cukup."""
    from src.core.analytics_ingest import ingest_all
    if not config.opt("IG_USER_ID"):
        raise HTTPException(status_code=409, detail="IG_USER_ID belum dikonfigurasi.")
    result = ingest_all(SessionLocal)
    if result.get("new_insights"):
        result["next_step"] = "Insight baru dari data nyata akan dipakai saat POST /api/v1/strategy/calendar/regenerate."
    return result


@app.get("/api/v1/health")
def health():
    return {"status": "ok", "scheduler_enabled": config.opt("SCHEDULER_ENABLED", "false").lower() == "true"}


@app.get("/api/v1/analytics/dashboard")
def get_analytics_dashboard_endpoint():
    """Mengambil data performa postingan dan rekomendasi insight berbasis metrik nyata/simulasi transparan."""
    with SessionLocal() as session:
        records = session.scalars(select(PostAnalytics).order_by(desc(PostAnalytics.id))).all()
        if not records and _demo_seed_allowed():
            records = seed_demo_analytics_data(session)
        insights = session.scalars(select(AnalyticsInsight).order_by(desc(AnalyticsInsight.id))).all()

        total_reach = sum(r.reach or 0 for r in records)
        total_likes = sum(r.likes or 0 for r in records)
        total_saves = sum(r.saves or 0 for r in records)
        total_comments = sum(r.comments or 0 for r in records)

        return {
            "summary": {
                "total_posts_tracked": len(records),
                "total_reach": total_reach,
                "total_engagement": total_likes + total_saves + total_comments,
                "total_saves": total_saves,
                "data_source": records[0].source if records else "none",
                "is_simulated": all(r.is_simulated for r in records) if records else False,
                "pending_ingestion": sum(r.ingestion_status == "pending" for r in records),
                "last_sync": next((r.data_timestamp.isoformat() for r in records if r.data_timestamp), None)
            },
            "posts": [
                {
                    "id": r.id,
                    "topic": r.topic,
                    "format": r.format,
                    "pillar": r.content_pillar,
                    "reach": r.reach,
                    "impressions": r.impressions,
                    "likes": r.likes,
                    "comments": r.comments,
                    "shares": r.shares,
                    "saves": r.saves,
                    "profile_visits": r.profile_visits,
                    "permalink": r.permalink,
                    "date": r.data_timestamp.strftime("%Y-%m-%d") if r.data_timestamp else None,
                    "source": r.source,
                    "is_simulated": r.is_simulated,
                    "ingestion_status": r.ingestion_status,
                }
                for r in records
            ],
            "insights": [
                {
                    "id": ins.id,
                    "title": ins.title,
                    "observation": ins.observation,
                    "recommended_action": ins.recommended_action,
                    "confidence": ins.confidence,
                    "data_points": json.loads(ins.data_points_json or "{}"),
                    "applied_to_strategy": ins.applied_to_strategy,
                    "created_at": ins.created_at.strftime("%Y-%m-%d")
                }
                for ins in insights
            ]
        }
