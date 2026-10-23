"""Registry layout: muat, validasi, dan beri katalog ringkas (tanpa HTML) untuk planner."""
from __future__ import annotations

import json
from pathlib import Path

from .models import LayoutError, LayoutSpec, parse_meta, parse_schema

LAYOUTS_DIR = Path(__file__).resolve().parent
_SKIP = {"primitives", "style", "__pycache__"}
REQUIRED_FILES = ("layout.html", "layout.css", "schema.json", "meta.json", "sample_data.json")


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LayoutError(f"{path}: JSON tidak valid ({exc})") from exc


def load_layout(folder: Path) -> LayoutSpec:
    missing = [f for f in REQUIRED_FILES if not (folder / f).exists()]
    if missing:
        raise LayoutError(f"{folder.name}: file wajib hilang {missing}")
    meta = parse_meta(_read_json(folder / "meta.json"), folder.name)
    slots, params = parse_schema(_read_json(folder / "schema.json"), folder.name)
    samples = _read_json(folder / "sample_data.json")
    for key in ("min", "typical", "max"):
        if key not in samples or "slots" not in samples[key]:
            raise LayoutError(f"{folder.name}: sample_data.json harus punya set '{key}' dengan 'slots'")
    return LayoutSpec(meta=meta, slots=slots, params=params, path=folder, samples=samples)


def load_all(root: Path | None = None) -> dict[str, LayoutSpec]:
    root = root or LAYOUTS_DIR
    found: dict[str, LayoutSpec] = {}
    for folder in sorted(p for p in root.iterdir() if p.is_dir() and p.name not in _SKIP and not p.name.startswith("_")):
        if not (folder / "meta.json").exists():
            continue
        spec = load_layout(folder)
        found[spec.id] = spec
    return found


def get(layout_id: str, root: Path | None = None) -> LayoutSpec:
    specs = load_all(root)
    if layout_id not in specs:
        raise LayoutError(f"layout '{layout_id}' tidak ada")
    return specs[layout_id]


def catalog(root: Path | None = None, statuses: tuple[str, ...] = ("approved",)) -> list[dict]:
    """Ringkasan untuk planner. Hanya status yang diizinkan; tanpa HTML/CSS."""
    out = []
    for spec in load_all(root).values():
        if spec.meta.status not in statuses:
            continue
        out.append({
            "id": spec.id, "role": spec.meta.role, "density": spec.meta.density,
            "needs_photo": spec.meta.needs_photo, "pose_tags": list(spec.meta.pose_tags),
            "tags": list(spec.meta.tags),
            "slots": {n: {"type": s.type, "required": s.required, "max_chars": s.max_chars,
                          "min_items": s.min_items, "max_items": s.max_items, "item_max_chars": s.item_max_chars}
                      for n, s in spec.slots.items()},
            "params": {n: list(p.enum) for n, p in spec.params.items()},
        })
    return out


def set_status(layout_id: str, status: str, root: Path | None = None) -> None:
    from .models import STATUSES
    if status not in STATUSES:
        raise LayoutError(f"status harus salah satu dari {STATUSES}")
    spec = get(layout_id, root)
    meta_path = spec.path / "meta.json"
    raw = _read_json(meta_path)
    raw["status"] = status
    meta_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
