"""Approve or reject a generated image after visual review."""
import argparse
from pathlib import Path

from src.carousel.tools import asset_library, cloudflare_pose_generator


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("asset_id", help="ID numerik dari list_assets, atau prefix hash/cache key asset")
    decision = parser.add_mutually_exclusive_group(required=True)
    decision.add_argument("--approve", action="store_true")
    decision.add_argument("--reject", action="store_true")
    args = parser.parse_args()
    status = "approved" if args.approve else "rejected"
    if status == "approved":
        selector = str(args.asset_id)
        asset = None
        if selector.isdecimal():
            asset = asset_library.get_asset(int(selector))
        else:
            asset = next((a for a in asset_library.pending_assets()
                          if (a.get("cache_key") or "").startswith(selector)), None)
        if not asset:
            parser.error(f"Pending asset tidak ditemukan: {selector}")
        qc = cloudflare_pose_generator.quality_check_generated(asset["path"])
        if not qc["ok"]:
            parser.error(f"Asset gagal QC otomatis: {qc['issues']}")
    resolved_id = asset_library.set_status(args.asset_id, status)
    print(f"Asset database ID {resolved_id}: {status}")
    if status == "approved":
        print("Catatan: approval ini hanya melepas gerbang QC otomatis; periksa wajah, tangan, seragam, dan APD secara visual sebelum publish.")


if __name__ == "__main__":
    main()
