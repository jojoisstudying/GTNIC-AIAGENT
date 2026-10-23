"""Review the final carousel and publish only after explicit POST confirmation."""
import json

from src import config
from src.agents import publisher
from src.tools import asset_library


def main() -> int:
    pending = asset_library.pending_assets()
    if pending:
        print("Belum bisa publish; asset masih menunggu review:")
        for asset in pending:
            print(f"  ID {asset['id']} | {','.join(asset['tags'])} | {asset['path']}")
        return 2

    plan_path = config.OUTPUT_DIR / "plan_latest.json"
    design_path = config.OUTPUT_DIR / "design_latest.json"
    if not plan_path.is_file() or not design_path.is_file():
        print("Plan/desain belum ada. Jalankan python -m scripts.run_all dulu.")
        return 2
    plan_out = json.loads(plan_path.read_text(encoding="utf-8"))
    design = json.loads(design_path.read_text(encoding="utf-8"))
    for slide in design.get("slides", []):
        photo = slide.get("photo_path")
        if slide.get("has_photo") and (not photo or not asset_library.is_cutout(photo)):
            print(f"Slide {slide.get('index')}: foto bukan cutout transparan. Render ulang/check Designer dulu.")
            return 2

    result = publisher.confirm_and_publish(plan_out, design)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
