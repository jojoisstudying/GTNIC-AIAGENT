"""Resume a run that was waiting for pending assets to be approved.

Usage:
  python scripts/resume_run.py <run_id>

Flow:
  1. Load the latest plan for the run
  2. Re-run designer (which will now find approved assets)
  3. Update design in DB
  4. If still has pending assets -> stop again
  5. If ready -> output success, ready for publish_approved
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select, func

from src import config
from src.agents import designer
from src.core.context import create_run_context
from src.core.db import SessionLocal, Design, Plan, Run


def main(argv: list[str]) -> int:
    if not argv or argv[0] in {"-h", "--help"}:
        print(__doc__)
        return 0

    run_id = argv[0]
    session = SessionLocal()
    try:
        run = session.get(Run, run_id)
        if not run:
            print(f"Run {run_id} tidak ditemukan")
            return 1

        if run.status not in {"awaiting_approval", "awaiting_assets", "ok", "failed"}:
            print(f"Run {run_id} status={run.status}, bukan menunggu asset")
            return 1

        # Get latest plan
        plan_row = session.execute(
            select(Plan).where(Plan.run_id == run_id).order_by(Plan.version.desc())
        ).scalars().first()
        if not plan_row:
            print("Tidak ada plan untuk run ini")
            return 1

        plan = json.loads(plan_row.plan_json)
        brand = json.loads((config.ROOT / "config" / "brand.json").read_text(encoding="utf-8"))

        print(f"== Resume run {run_id} ==")
        print(f"Topic: {run.topic}")
        print(f"Plan version: {plan_row.version}")
        print(f"Slides: {len(plan.get('slides', []))}")

        # Create context linked to existing run
        ctx = create_run_context(run.topic, brand, run_id=run_id)
        ctx.llm.tokens_in = run.tokens_in
        ctx.llm.tokens_out = run.tokens_out
        ctx.llm.cost_usd = run.cost_usd

        try:
            design_result = designer.run(plan, brand, config.OUTPUT_DIR / "slides", ctx=ctx)

            # Save design version
            design_version = session.execute(
                select(func.max(Design.version)).where(Design.run_id == run_id)
            ).scalar() or 0

            design_row = Design(
                run_id=run_id,
                plan_id=plan_row.id,
                version=design_version + 1,
                ok=bool(design_result.get("ok")),
                result_json=json.dumps(design_result, ensure_ascii=False),
                preview_path=design_result.get("preview"),
            )
            session.add(design_row)
            session.commit()

            # Export versioned JSON
            run_dir = config.OUTPUT_DIR / "runs" / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / f"design_v{design_version + 1}.json").write_text(
                json.dumps(design_result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (config.OUTPUT_DIR / "design_latest.json").write_text(
                json.dumps(design_result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (config.OUTPUT_DIR / "plan_latest.json").write_text(
                json.dumps({"ok": plan_row.ok, "plan": plan, "issues": json.loads(plan_row.issues_json or "[]")},
                           ensure_ascii=False, indent=2), encoding="utf-8"
            )

            # Update run status
            if design_result.get("pending_review"):
                run.status = "awaiting_assets"
                print("\nMasih ada asset pending review:")
                for a in design_result["pending_review"]:
                    print(f"  ID {a['id']} | pose={a['pose']} | QC={'OK' if a.get('qc', {}).get('ok') else 'GAGAL'}")
                    print(f"    file: {a['path']}")
                print("\nApprove asset lalu jalankan resume_run lagi.")
            elif design_result.get("missing_poses"):
                run.status = "awaiting_assets"
                print(f"\nPose belum tersedia: {design_result['missing_poses']}")
                print("Aktifkan CLOUDFLARE_POSE_GENERATION=true dan pastikan person_id disetel, lalu ulangi.")
            else:
                run.status = "ok"
                print(f"\nDesain selesai. Preview: {design_result['preview']}")
                print("Untuk review publish dan posting, jalankan:")
                print("  python -m scripts.publish_approved")

            run.finished_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
            run.tokens_in = ctx.llm.tokens_in
            run.tokens_out = ctx.llm.tokens_out
            run.cost_usd = ctx.llm.cost_usd
            session.commit()

            return 0 if run.status == "ok" else 2

        except Exception as exc:
            run.status = "failed"
            run.finished_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
            run.error = type(exc).__name__
            session.commit()
            print(f"Error: {exc}")
            return 1
        finally:
            ctx.close()
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))