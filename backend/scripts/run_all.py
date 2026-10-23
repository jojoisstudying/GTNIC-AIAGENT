"""End-to-end pipeline: research -> plan -> generate/cutout -> design QC -> review gate.

Example: python -m scripts.run_all "tips keselamatan kerja"
Use --fresh to rerun research. This command never publishes; use publish after review.
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import config, pipeline
from src.agents import designer
from src.tools import asset_library


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("topic", nargs="?", default="tips keselamatan kerja di area produksi")
    parser.add_argument("--fresh", action="store_true", help="Rerun research before planning")
    parser.add_argument("--no-generate", action="store_true", help="Use existing approved assets only")
    args = parser.parse_args()

    # `run_all` is the full asset-producing workflow. Respect `--no-generate` only as an explicit opt-out;
    # do not let a stale .env CLOUDFLARE_POSE_GENERATION=false silently turn it into placeholder-only mode.
    os.environ["CLOUDFLARE_POSE_GENERATION"] = "false" if args.no_generate else "true"

    print("== Agent 1 + 2: Research / Planner ==")
    plan_out = pipeline.run(args.topic, fresh=args.fresh, include_design=True)
    if not plan_out.get("ok"):
        print("Rencana gagal validasi:", plan_out.get("issues"))
        return 1

    print("== Agent 3: generate assets / cutout / render + QC ==")
    design = plan_out["design"]
    pending = asset_library.pending_assets()
    print("Preview:", design["preview"])
    if pending:
        print("\nAsset menunggu review:")
        for asset in pending:
            qc_result = designer.cloudflare_pose_generator.quality_check_generated(asset["path"])
            print(f"  ID {asset['id']} | pose={','.join(asset['tags'])} | QC={'OK' if qc_result['ok'] else 'GAGAL'}")
            print(f"    file: {asset['path']}")
            for issue in qc_result["issues"]:
                print("    QC:", issue)
        print("\nPeriksa file di atas. Approve asset yang lolos QC dengan scripts.approve_asset, lalu jalankan:")
        print(f"  python scripts/resume_run.py {plan_out.get('run_id', '<run_id>')}")
        print("Pipeline berhenti sebelum publish. Tidak ada posting otomatis.")
        return 2

    if design.get("missing_poses"):
        print("Pose belum tersedia:", design["missing_poses"])
        print("Aktifkan generation Cloudflare dan pastikan foto referensi terdaftar, lalu ulangi.")
        return 2
    print("Desain selesai. Tidak ada asset pending. Untuk review publish dan posting, jalankan:")
    print("  python -m scripts.publish_approved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())