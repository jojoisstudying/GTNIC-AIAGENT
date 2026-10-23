"""Render contact sheet uji tekanan per batch.

  python scripts/render_gallery.py --batch 1
  python scripts/render_gallery.py --layout cover_judul_raksasa

Per layout: 3 panjang teks (min/typical/max) x 3 seed (2 dark + 1 light) = 9 render.
Keluaran: gallery/batch_N/{contact_sheet_<id>.jpg, overview.jpg, report.md}
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.layouts import registry  # noqa: E402
from src.layouts.style.packs import build_pack  # noqa: E402
from src.render.assemble import render_layout_html  # noqa: E402
from src.render.renderer import Renderer  # noqa: E402
from src.tools import qc_dom  # noqa: E402

FONT = ROOT / "src/render/fonts/Poppins-Medium.ttf"
FIXTURES = ROOT / "src/layouts/_fixtures"
CELL_W, CELL_H, GAP, LABEL = 420, 525, 18, 34
SETS = ("min", "typical", "max")
TOTAL = 5


def pick_seeds(brand: dict) -> list[tuple[int, str]]:
    """Dua seed dark dan satu seed light, deterministik."""
    want = {"dark": 2, "light": 1}
    picked: list[tuple[int, str]] = []
    seed = 1
    while any(want.values()) and seed < 500:
        surface = build_pack(seed, brand, TOTAL)["surface"]
        if want[surface] > 0:
            want[surface] -= 1
            picked.append((seed, surface))
        seed += 1
    return sorted(picked, key=lambda p: p[1] != "dark")


def _label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, fill=(210, 210, 210)) -> None:
    draw.text(xy, text, font=ImageFont.truetype(str(FONT), 18), fill=fill)


def _photo_url(sample: dict) -> str | None:
    name = sample.get("photo")
    return (FIXTURES / f"{name}.png").as_uri() if name else None


def run_variant(r: Renderer, spec, brand: dict, out_dir: Path, with_photo: bool | None, suffix: str) -> dict:
    seeds = pick_seeds(brand)
    index = 0 if spec.meta.role == "cover" else 2
    results, issues_by_cell = {}, {}
    for si, (seed, surface) in enumerate(seeds):
        pack = build_pack(seed, brand, TOTAL, force_surface=surface)
        for set_name in SETS:
            sample = spec.samples[set_name]
            photo = _photo_url(sample) if with_photo else None
            html = render_layout_html(spec, sample["slots"], sample.get("params", {}), sample.get("emphasis", []),
                                      pack, index, TOTAL, brand, photo_url=photo)
            path = out_dir / "slides" / f"{spec.id}{suffix}__{set_name}__s{seed}.jpg"
            res = r.render(html, path)
            results[(si, set_name)] = path
            issues_by_cell[(si, set_name)] = qc_dom.evaluate(res.report)
    cols, rows = len(SETS), len(seeds)
    w = cols * CELL_W + (cols + 1) * GAP
    h = rows * (CELL_H + LABEL) + (rows + 1) * GAP + 40
    sheet = Image.new("RGB", (w, h), (26, 26, 26))
    d = ImageDraw.Draw(sheet)
    tag = {True: "dengan foto", False: "tanpa foto", None: ""}[with_photo]
    _label(d, (GAP, 10), f"{spec.id} {tag}  |  role={spec.meta.role}  status={spec.meta.status}")
    for (si, set_name), path in results.items():
        ci = SETS.index(set_name)
        x = GAP + ci * (CELL_W + GAP)
        y = 40 + GAP + si * (CELL_H + LABEL + GAP)
        ok = qc_dom.passed(issues_by_cell[(si, set_name)])
        _label(d, (x, y), f"{set_name} | seed {seeds[si][0]} {seeds[si][1]} | {'OK' if ok else 'GAGAL'}",
               (120, 220, 140) if ok else (255, 120, 120))
        im = Image.open(path).resize((CELL_W, CELL_H), Image.LANCZOS)
        sheet.paste(im, (x, y + LABEL))
    sheet_path = out_dir / f"contact_sheet_{spec.id}{suffix}.jpg"
    sheet.save(sheet_path, "JPEG", quality=88)
    return {"sheet": sheet_path, "overview": results[(0, "typical")], "issues_by_cell": issues_by_cell, "seeds": seeds}


def run_layout(r: Renderer, spec, brand: dict, out_dir: Path) -> dict:
    need = spec.meta.needs_photo
    variants = {"required": [(True, "")], "optional": [(True, ""), (False, "__tanpa_foto")], "none": [(None, "")]}[need]
    parts = [run_variant(r, spec, brand, out_dir, wp, sfx) for wp, sfx in variants]
    all_issues = [(k, i) for p in parts for k, lst in p["issues_by_cell"].items() for i in lst]
    return {"spec": spec, "sheet": parts[0]["sheet"], "sheets": [p["sheet"] for p in parts],
            "seeds": parts[0]["seeds"], "issues": all_issues, "overview": parts[0]["overview"],
            "passed": all(qc_dom.passed(v) for p in parts for v in p["issues_by_cell"].values())}


def write_report(out_dir: Path, outcomes: list[dict], title: str) -> None:
    lines = [f"# Report {title}", "", "| layout | role | status | gerbang otomatis | catatan |", "|---|---|---|---|---|"]
    for o in outcomes:
        s = o["spec"]
        errors = [(k, i) for k, i in o["issues"] if i.severity == "error"]
        warns = [(k, i) for k, i in o["issues"] if i.severity == "warn"]
        note = "; ".join(sorted({f"{i.code}@{i.element}" for _, i in errors}))[:200] or "-"
        if warns:
            note += " | warn: " + ", ".join(sorted({i.code for _, i in warns}))
        lines.append(f"| {s.id} | {s.meta.role} | {s.meta.status} | {'LOLOS' if o['passed'] else 'GAGAL OTOMATIS'} | {note} |")
    lines += ["", "Gerbang otomatis: tidak overflow, font >= minimum, kontras, margin aman, tidak menabrak chrome, "
              "tidak tumpang tindih. Penilaian selera tetap oleh pemilik proyek."]
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_overview(out_dir: Path, outcomes: list[dict]) -> None:
    ims = [Image.open(o["overview"]).resize((CELL_W, CELL_H), Image.LANCZOS) for o in outcomes]
    cols = min(4, len(ims))
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * CELL_W + (cols + 1) * GAP, rows * (CELL_H + LABEL) + (rows + 1) * GAP), (26, 26, 26))
    d = ImageDraw.Draw(sheet)
    for i, (im, o) in enumerate(zip(ims, outcomes)):
        x, y = GAP + (i % cols) * (CELL_W + GAP), GAP + (i // cols) * (CELL_H + LABEL + GAP)
        _label(d, (x, y), o["spec"].id)
        sheet.paste(im, (x, y + LABEL))
    sheet.save(out_dir / "overview.jpg", "JPEG", quality=88)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--batch", type=int)
    ap.add_argument("--layout")
    args = ap.parse_args()
    brand = json.loads((ROOT / "config/brand.json").read_text(encoding="utf-8"))
    specs = registry.load_all()
    if args.layout:
        chosen, title = [specs[args.layout]], f"layout_{args.layout}"
    elif args.batch is not None:
        chosen, title = [s for s in specs.values() if s.meta.batch == args.batch], f"batch_{args.batch}"
    else:
        ap.error("pakai --batch N atau --layout ID")
    if not chosen:
        print("Tidak ada layout yang cocok.")
        return 1
    out_dir = ROOT / "gallery" / title
    out_dir.mkdir(parents=True, exist_ok=True)
    with Renderer() as r:
        outcomes = [run_layout(r, s, brand, out_dir) for s in chosen]
    write_report(out_dir, outcomes, title)
    write_overview(out_dir, outcomes)
    for o in outcomes:
        print(f"{o['spec'].id}: {'LOLOS' if o['passed'] else 'GAGAL OTOMATIS'} -> {o['sheet']}")
    print(f"report: {out_dir / 'report.md'}")
    return 0 if all(o["passed"] for o in outcomes) else 3


if __name__ == "__main__":
    raise SystemExit(main())
