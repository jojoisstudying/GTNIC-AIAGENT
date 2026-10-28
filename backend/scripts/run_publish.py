"""Posting dari hasil terakhir (output/plan_latest.json + output/design_latest.json).
Cek tanpa memposting :  python -m scripts.run_publish --dry-run
Posting (minta konfirmasi): python -m scripts.run_publish
Opsi: --yes (lewati konfirmasi), --allow-placeholder (hanya tes di akun demo)"""
import json
import sys
from src import config
from src.carousel.agents import publisher

plan_out = json.loads((config.OUTPUT_DIR / "plan_latest.json").read_text(encoding="utf-8"))
design = json.loads((config.OUTPUT_DIR / "design_latest.json").read_text(encoding="utf-8"))
res = publisher.confirm_and_publish(plan_out, design, yes="--yes" in sys.argv,
                                    allow_placeholder="--allow-placeholder" in sys.argv,
                                    dry_run="--dry-run" in sys.argv)
sys.exit(0 if res.get("ok") else 1)