"""FastAPI entrypoint for Social Media Automation AI Agent.

Provides endpoints for frontend dashboard integration:
- Trigger run (Research -> Plan -> Design)
- Run status & events monitoring (polling / event stream)
- Layout catalog listing
- Direct publishing to Instagram
- Static asset / slide image preview serving
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, desc, func

from src import config, pipeline
from src.core.context import create_run_context
from src.core.db import Run, Plan, Design, Event, Publication, SessionLocal
from src.layouts import registry

app = FastAPI(
    title="GTNIC Social Media AI Agent API",
    version="1.0.0",
    description="Enterprise-grade AI Social Media Post Generator (No AI Slop)"
)

# Enable CORS for Frontend development (Next.js/Vite/localhost)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
    target_duration: int = Field(30, description="Target durasi video dalam detik")


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
        print(f"[API ERROR] Pipeline execution failed for run {run_id}: {e}")
    finally:
        ctx.close()


def _execute_resume_task(run_id: str):
    """Worker task to resume run after assets have been approved."""
    from src.agents import designer
    with SessionLocal() as session:
        run = session.get(Run, run_id)
        if not run:
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
        design_result = designer.run(plan, brand, config.OUTPUT_DIR / "runs" / run_id / "slides", ctx=ctx)
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
                preview_path=design_result.get("preview")
            )
            session.add(design_row)

            run_row = session.get(Run, run_id)
            if design_result.get("pending_review"):
                run_row.status = "awaiting_approval"
            elif design_result.get("missing_poses"):
                run_row.status = "awaiting_assets"
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
        print(f"[RESUME ERROR] {e}")
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
    from src.tools import cloudflare_pose_generator

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
        print(f"[REGENERATE ERROR] asset {asset_id} pose {pose}: {e}")
        if run_id:
            try:
                with SessionLocal() as session:
                    run_row = session.get(Run, run_id)
                    if run_row:
                        run_row.status = "awaiting_assets"
                        run_row.error = f"Regenerate pose '{pose}' gagal: {e}"
                        session.commit()
            except Exception as db_exc:
                print(f"[REGENERATE ERROR] gagal mengembalikan status run {run_id}: {db_exc}")
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


def _execute_video_pipeline_task(run_id: str, topic: str, duration: int):
    """Worker task executing video pipeline; selalu menutup run dengan status ok/failed."""
    import asyncio
    from src.video.pipeline import VideoPipeline

    brand = pipeline.load_brand()
    ctx = create_run_context(topic, brand, run_id=run_id)
    try:
        ctx.emit("info", "run_started", step="video", detail={"topic": topic, "format": "video"})
        out_path = config.OUTPUT_DIR / "reels" / f"reels_{run_id}.mp4"

        vp = VideoPipeline(context=ctx)
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
        error = None if result.ok else "; ".join(result.issues) or "QC video gagal"
        _save_video_result(run_id, payload, status, ctx=ctx, error=error)
        ctx.emit("info", "run_finished", step="video", status=status,
                 tokens_in=ctx.llm.tokens_in, tokens_out=ctx.llm.tokens_out,
                 cost_usd=ctx.llm.cost_usd)
    except Exception as e:
        print(f"[API ERROR] Video pipeline execution failed for run {run_id}: {e}")
        try:
            _save_video_result(
                run_id,
                {"type": "video", "ok": False, "video_path": None, "issues": [str(e)]},
                "failed", ctx=ctx, error=f"{type(e).__name__}: {e}",
            )
        except Exception as db_exc:  # jangan sampai kegagalan DB menyembunyikan error asli
            print(f"[API ERROR] Gagal menyimpan status failed untuk run {run_id}: {db_exc}")
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/brand")
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/brand/logo")
def upload_brand_logo(file: UploadFile = File(...)):
    """Upload logo brand dan simpan ke assets/logo.png."""
    try:
        assets_dir = config.ROOT / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        logo_path = assets_dir / "logo.png"

        contents = file.file.read()
        logo_path.write_bytes(contents)

        # Update brand.json logo_path
        brand_file = config.ROOT / "config" / "brand.json"
        if brand_file.exists():
            brand_data = json.loads(brand_file.read_text(encoding="utf-8"))
            brand_data["logo_path"] = "assets/logo.png"
            brand_file.write_text(json.dumps(brand_data, indent=2, ensure_ascii=False), encoding="utf-8")

        return {"status": "ok", "message": "Logo berhasil disimpan", "path": "assets/logo.png"}
    except Exception as e:
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


@app.post("/api/v1/runs/generate")
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
    from src.tools import asset_library

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
                    from src.tools import asset_library as _al
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


@app.post("/api/v1/runs/{run_id}/publish")
def publish_run_to_instagram(run_id: str):
    """Mempublikasikan carousel yang sudah di-generate langsung ke Instagram feed."""
    from src.agents import publisher

    brand = pipeline.load_brand()
    with SessionLocal() as session:
        run_row = session.get(Run, run_id)
        if not run_row:
            raise HTTPException(status_code=404, detail="Run tidak ditemukan")

        plan_row = session.scalars(
            select(Plan).where(Plan.run_id == run_id).order_by(desc(Plan.version))
        ).first()
        design_row = session.scalars(
            select(Design).where(Design.run_id == run_id).order_by(desc(Design.version))
        ).first()

        if design_row and json.loads(design_row.result_json or "{}").get("type") == "video":
            raise HTTPException(
                status_code=400,
                detail="Publish Reels ke Instagram belum didukung. Video bisa diunduh dari preview.",
            )
        if not plan_row or not design_row:
            raise HTTPException(status_code=400, detail="Plan atau Desain untuk run ini belum siap.")

        plan_data = json.loads(plan_row.plan_json)
        design_data = json.loads(design_row.result_json)

    # Eksekusi publishing via publisher agent
    ctx = create_run_context(run_row.topic, brand, run_id=run_id)
    try:
        # Panggil preflight sebelum publish
        problems = publisher.preflight(plan_data, design_data, session=ctx.session, ctx=ctx)
        if problems:
            raise HTTPException(status_code=400, detail="; ".join(problems))

        slide_paths = [s["path"] for s in design_data.get("slides", [])]
        result = publisher.publish(plan_data, slide_paths, ctx=ctx)
        is_ok = bool(result.get("ok")) or bool(result.get("media_id"))
        return {
            "run_id": run_id,
            "status": "published" if is_ok else "failed",
            "media_id": result.get("media_id"),
            "permalink": result.get("permalink"),
            "error": result.get("error")
        }
    except Exception as e:
        print(f"[PUBLISH ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        ctx.close()


@app.post("/api/v1/assets/{asset_id}/review")
def review_pending_asset(asset_id: int, status: str = "approved"):
    """Menyetujui (approve) atau menolak (reject) pose hasil generate Cloudflare."""
    from src.tools import asset_library, cloudflare_pose_generator
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


@app.post("/api/v1/runs/{run_id}/resume")
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


@app.post("/api/v1/assets/{asset_id}/regenerate")
def regenerate_pose_endpoint(asset_id: int, req: RegeneratePoseRequest,
                             background_tasks: BackgroundTasks):
    """Buat ulang pose yang ditolak (kandidat baru, tetap perlu review manusia).

    - Jika run terkait sedang menunggu (awaiting_approval/awaiting_assets): kandidat baru dibuat
      lalu run dilanjutkan otomatis sehingga kembali ke 'awaiting_approval'.
    - Jika tidak ada run yang menunggu: hanya membuat kandidat baru di Asset Library.
    Proses berjalan di background (generate gambar + hapus background bisa >1 menit).
    """
    from src.tools import asset_library, cloudflare_pose_generator

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


@app.post("/api/v1/assets/upload")
def upload_talent_reference(
    file: UploadFile = File(...),
    person_id: str = Form("operator_01"),
    description: str = Form("Foto mentah orang tanpa pose sebagai referensi AI")
):
    """Upload mentahan foto orang tanpa pose untuk referensi Cloudflare Workers AI."""
    from src.tools.asset_library import add_asset
    try:
        people_dir = config.ROOT / "data" / "people" / person_id
        people_dir.mkdir(parents=True, exist_ok=True)
        dest_path = people_dir / "reference.png"

        contents = file.file.read()
        dest_path.write_bytes(contents)

        # Daftarkan juga ke asset_library agar langsung muncul di Asset Library UI
        asset_id = add_asset(
            path=str(dest_path),
            tags=["mentahan", "reference", person_id],
            description=description,
            status="approved",
            person_id=person_id,
            kind="reference"
        )

        return {
            "status": "ok",
            "message": f"Foto referensi mentah untuk person '{person_id}' berhasil diupload",
            "path": str(dest_path),
            "asset_id": asset_id,
            "person_id": person_id
        }
    except Exception as e:
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
    from src.tools.asset_library import list_assets

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


@app.post("/api/v1/runs/generate-video")
def create_video_run(req: VideoRunRequest, background_tasks: BackgroundTasks):
    """Memicu pipeline pembuatan short-form video vertikal (Script -> TTS -> B-Roll -> Assembly -> QC)."""
    brand = pipeline.load_brand()
    ctx = create_run_context(req.topic, brand)
    run_id = ctx.run_id
    ctx.close()

    background_tasks.add_task(_execute_video_pipeline_task, run_id, req.topic, req.target_duration)

    return {
        "run_id": run_id,
        "status": "running",
        "topic": req.topic,
        "message": "AI Agent sedang memproses naskah, voiceover TTS, B-roll, dan compositing video."
    }