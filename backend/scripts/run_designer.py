"""Jalankan Agent 3 dari rencana tersimpan (output/plan_latest.json).
Pakai python scripts/run_designer.py (langsung) atau python scripts/resume_run.py <run_id> (untuk lanjutkan run yang menunggu asset).
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


def main() -> int:
    saved = json.loads((config.OUTPUT_DIR / "plan_latest.json").read_text(encoding="utf-8"))
    if not saved.get("plan"):
        raise SystemExit("plan_latest.json tidak berisi rencana. Jalankan scripts.run_planner dulu.")

    # Get run_id from saved plan if exists
    run_id = saved.get("run_id")
    brand = json.loads((config.ROOT / "config" / "brand.json").read_text(encoding="utf-8"))

    if run_id:
        # Resume existing run
        session = SessionLocal()
        try:
            run = session.get(Run, run_id)
            if run:
                ctx = create_run_context(run.topic, brand, run_id=run_id)
                ctx.llm.tokens_in = run.tokens_in
                ctx.llm.tokens_out = run.tokens_out
                ctx.llm.cost_usd = run.cost_usd
            else:
                ctx = create_run_context(saved.get("topic", "unknown"), brand)
        finally:
            session.close()
    else:
        ctx = create_run_context(saved.get("topic", "unknown"), brand)

    try:
        res = designer.run(saved["plan"], brand, config.OUTPUT_DIR / "runs" / ctx.run_id / "slides", ctx=ctx)

        print("\n===== HASIL DESIGNER (AGENT 3) =====")
        for m in res["slides"]:
            flag = "OK " if not m["issues"] else "!! "
            print(f"{flag}slide {m['index']} [{m['role']}] headline {m['headline_size']}px, subtext {m['subtext_size']}px"
                  f"{' | foto placeholder' if m['placeholder'] else ''}")
            for i in m["issues"]:
                print("     -", i)
        for w in res["warnings"]:
            print("PERINGATAN:", w)
        print("\nStatus QC kode:", "LOLOS" if res["ok"] else "ADA MASALAH")
        print("Slide: output/slides/slide_XX.jpg | Pratinjau gabungan:", res["preview"])

        if res.get("pending_review"):
            print("\nAsset menunggu review:")
            for a in res["pending_review"]:
                print(f"  ID {a['id']} | pose={a['pose']} | QC={'OK' if a.get('qc', {}).get('ok') else 'GAGAL'}")
                print(f"    file: {a['path']}")
            print("\nApprove asset lalu jalankan:")
            print(f"  python scripts/resume_run.py {ctx.run_id}")
            return 2

        return 0 if res["ok"] else 1
    finally:
        ctx.close()


if __name__ == "__main__":
    raise SystemExit(main())