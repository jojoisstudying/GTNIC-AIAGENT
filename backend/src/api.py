"""FastAPI entrypoint for Social Media Automation AI Agent.

Provides endpoints for frontend dashboard integration:
- Trigger run (Research -> Plan -> Design)
- Run status & events monitoring (polling / event stream)
- Layout catalog listing
- Direct publishing to Instagram
- Static asset / slide image preview serving
"""
import json
from pathlib import Path
from typing import Any, Optional
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, desc

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
app.mount("/static/output", StaticFiles(directory=str(config.OUTPUT_DIR)), name="output")


# --- Request & Response Models ---

class TriggerRunRequest(BaseModel):
    topic: str = Field(..., description="Topik atau tema konten media sosial yang ingin dibuat")
    fresh: bool = Field(True, description="True untuk melakukan riset web baru (Tavily), False untuk pakai cache")
    include_design: bool = Field(True, description="True untuk merender gambar carousel (Playwright/HTML)")


class PublishRequest(BaseModel):
    run_id: str = Field(..., description="UUID hex dari run yang ingin dipublish")


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
        return pipeline.load_brand()
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

        # Ubah path lokal slides menjadi URL statis yang bisa langsung ditampilkan browser frontend
        slides_preview = []
        if design_data and "slides" in design_data:
            for s in design_data["slides"]:
                local_path = s.get("path")
                if local_path:
                    # Ambil relative path terhadap output/
                    rel_path = Path(local_path).relative_to(config.OUTPUT_DIR) if str(config.OUTPUT_DIR) in str(local_path) else Path(local_path).name
                    s_copy = dict(s)
                    s_copy["image_url"] = f"/static/output/{rel_path}"
                    slides_preview.append(s_copy)

        return {
            "run_id": run_row.id,
            "topic": run_row.topic,
            "status": run_row.status,
            "started_at": run_row.started_at.isoformat() if run_row.started_at else None,
            "finished_at": run_row.finished_at.isoformat() if run_row.finished_at else None,
            "tokens_in": run_row.tokens_in or 0,
            "tokens_out": run_row.tokens_out or 0,
            "cost_usd": run_row.cost_usd or 0.0,
            "error": run_row.error,
            "plan": plan_data,
            "design": {
                "ok": design_row.ok if design_row else False,
                "slides": slides_preview,
                "preview_path": f"/static/output/{Path(design_row.preview_path).name}" if design_row and design_row.preview_path else None
            } if design_row else None
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

        if not plan_row or not design_row:
            raise HTTPException(status_code=400, detail="Plan atau Desain untuk run ini belum siap.")

        plan_data = json.loads(plan_row.plan_json)
        design_data = json.loads(design_row.result_json)

    # Eksekusi publishing via publisher agent
    ctx = create_run_context(run_row.topic, brand, run_id=run_id)
    try:
        result = publisher.run(plan_data, design_data, brand, ctx=ctx)
        return {
            "run_id": run_id,
            "status": "published" if result.get("ok") else "failed",
            "media_id": result.get("media_id"),
            "permalink": result.get("permalink"),
            "error": result.get("error")
        }
    finally:
        ctx.close()
