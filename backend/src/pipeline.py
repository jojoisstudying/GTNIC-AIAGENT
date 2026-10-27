"""Orchestrate research, planning, and design with run-scoped persistence."""
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select

from src import config
from src.agents import designer, research_agent, planner
from src.core.context import RunContext, create_run_context
from src.core.db import Design, Plan, ResearchSnapshot, Run

RESEARCH_FILE = config.OUTPUT_DIR / "research_latest.json"
PLAN_FILE = config.OUTPUT_DIR / "plan_latest.json"


def _export_run_version(run_id: str, name: str, version: int, payload: dict) -> Path:
    """Write an immutable per-run JSON export while preserving the compatibility latest copy."""
    run_dir = config.OUTPUT_DIR / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    version_path = run_dir / f"{name}_v{version}.json"
    version_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return version_path


def load_brand() -> dict:
    return json.loads((config.ROOT / "config" / "brand.json").read_text(encoding="utf-8"))


def load_saved_research() -> dict:
    if not RESEARCH_FILE.exists():
        raise RuntimeError("output/research_latest.json belum ada. Jalankan dengan --fresh dulu.")
    saved = json.loads(RESEARCH_FILE.read_text(encoding="utf-8"))
    if not saved.get("ok"):
        raise RuntimeError("Hasil riset tersimpan tidak valid (ok=false). Jalankan ulang dengan --fresh.")
    return saved["data"]


def _close_run(session, ctx: RunContext, status: str, error: str | None = None):
    """Tulis status akhir + token/cost ke tabel runs. Dipakai SEMUA jalur keluar run()."""
    run_row = session.get(Run, ctx.run_id)
    if run_row:
        run_row.status = status
        run_row.error = error
        run_row.finished_at = datetime.now(timezone.utc)
        run_row.tokens_in = ctx.llm.tokens_in
        run_row.tokens_out = ctx.llm.tokens_out
        run_row.cost_usd = ctx.llm.cost_usd
        session.commit()
    return run_row


def run(topic: str, fresh: bool = False, on_step=print, *, ctx: RunContext | None = None,
        include_design: bool = False) -> dict:
    brand = load_brand()
    own_context = ctx is None
    ctx = ctx or create_run_context(topic, brand)
    session = ctx.session
    try:
        ctx.emit("info", "run_started", step="pipeline", detail={"topic": topic})
        if fresh:
            on_step("== Agent 1: Research ==")
            res = research_agent.run(topic, brand.get("industry", ""), on_step=on_step, ctx=ctx,
                                     brand_facts=brand.get("verified_facts"))
            session.add(ResearchSnapshot(run_id=ctx.run_id,
                data_json=json.dumps(res.get("data"), ensure_ascii=False),
                warnings_json=json.dumps(res.get("warnings", []), ensure_ascii=False), ok=bool(res.get("ok"))))
            session.commit()
            research_version = session.scalar(select(func.count(ResearchSnapshot.id)).where(
                ResearchSnapshot.run_id == ctx.run_id))
            _export_run_version(ctx.run_id, "research", research_version or 1, res)
            RESEARCH_FILE.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
            ctx.emit("info", "research_saved", step="research", status="ok",
                     detail={"ok": bool(res.get("ok"))})
            if not res["ok"]:
                raise RuntimeError("Agent 1 gagal menghasilkan JSON valid. Lihat output/research_latest.json")
            research = res["data"]
        else:
            on_step("== Agent 1: memakai hasil riset tersimpan (hemat kuota) ==")
            research = load_saved_research()
            session.add(ResearchSnapshot(run_id=ctx.run_id,
                data_json=json.dumps(research, ensure_ascii=False), warnings_json="[]", ok=True))
            session.commit()
            research_version = session.scalar(select(func.count(ResearchSnapshot.id)).where(
                ResearchSnapshot.run_id == ctx.run_id))
            research_export = {"ok": True, "data": research, "warnings": []}
            _export_run_version(ctx.run_id, "research", research_version or 1, research_export)

        on_step("== Agent 2: Planner ==")
        out = planner.run(topic, research, brand, on_step=on_step, ctx=ctx)
        version = session.scalar(select(func.max(Plan.version)).where(Plan.run_id == ctx.run_id)) or 0
        plan_row = Plan(run_id=ctx.run_id, version=version + 1, ok=bool(out.get("ok")),
                        plan_json=json.dumps(out.get("plan"), ensure_ascii=False),
                        issues_json=json.dumps(out.get("issues", []), ensure_ascii=False))
        session.add(plan_row)
        session.commit()
        _export_run_version(ctx.run_id, "plan", plan_row.version, out)
        ctx.emit("info", "plan_saved", step="planner", status="ok" if out.get("ok") else "failed",
             detail={"version": plan_row.version, "ok": bool(out.get("ok"))})
        PLAN_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

        if not out.get("ok"):
            # FIX: dulu langsung `return out` -> run stuck 'running' selamanya.
            print("Rencana gagal validasi:", out.get("issues"))
            msg = "Rencana gagal validasi: " + "; ".join(str(i) for i in (out.get("issues") or [])[:5])
            _close_run(session, ctx, "failed", msg)
            ctx.emit("error", "planner", step="planner", status="failed",
                     detail={"issues": out.get("issues", [])})
            out["run_id"] = ctx.run_id
            return out

        if include_design and out.get("plan"):
            design_result = designer.run(out["plan"], brand, config.OUTPUT_DIR / "slides", ctx=ctx)
            design_version = session.scalar(select(func.max(Design.version)).where(Design.run_id == ctx.run_id)) or 0
            session.add(Design(run_id=ctx.run_id, plan_id=plan_row.id, version=design_version + 1,
                               ok=bool(design_result.get("ok")),
                               result_json=json.dumps(design_result, ensure_ascii=False),
                               preview_path=design_result.get("preview")))
            session.commit()
            _export_run_version(ctx.run_id, "design", design_version + 1, design_result)
            (config.OUTPUT_DIR / "design_latest.json").write_text(
                json.dumps(design_result, ensure_ascii=False, indent=2), encoding="utf-8")
            out["design"] = design_result
            ctx.emit("info", "design_saved", step="designer", status="ok" if design_result.get("ok") else "failed",
                     detail={"version": design_version + 1, "ok": bool(design_result.get("ok"))})

        # FIX: samakan dengan _execute_resume_task di api.py (pose belum ada -> awaiting_assets)
        design_out = out.get("design") or {}
        if design_out.get("pending_review"):
            status = "awaiting_approval"
        elif design_out.get("missing_poses"):
            status = "awaiting_assets"
        else:
            status = "ok"
        run_row = _close_run(session, ctx, status)
        if run_row:
            ctx.emit("info", "run_finished", step="pipeline", status=run_row.status,
                     tokens_in=run_row.tokens_in, tokens_out=run_row.tokens_out,
                     cost_usd=run_row.cost_usd)
        out["run_id"] = ctx.run_id
        return out
    except Exception as exc:
        try:
            session.rollback()  # session bisa dalam state gagal kalau error datang dari DB
            _close_run(session, ctx, "failed", f"{type(exc).__name__}: {exc}")
            ctx.emit("error", "pipeline", step="pipeline", status="failed",
                     detail={"error": str(exc), "error_type": type(exc).__name__})
        except Exception as inner:
            print(f"[PIPELINE] gagal menandai run {ctx.run_id} failed: {inner}")
        raise
    finally:
        if own_context:
            ctx.close()