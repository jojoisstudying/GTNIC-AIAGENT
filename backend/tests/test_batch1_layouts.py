"""Semua layout Batch 1 harus lolos gerbang otomatis (dark + light, min/typical/max, dengan/tanpa foto)."""
import json
from pathlib import Path

import pytest

from src.carousel.layouts import registry
from src.carousel.layouts.models import validate_content
from src.carousel.layouts.primitives.icons import ICON_NAMES, icon_svg
from src.carousel.layouts.style.packs import build_pack
from src.carousel.render.assemble import emph_html, render_layout_html
from src.carousel.render.renderer import RenderError, Renderer
from src.carousel.tools import qc_dom

ROOT = Path(__file__).resolve().parents[1]
BRAND = json.loads((ROOT / "config" / "brand.json").read_text(encoding="utf-8"))
FIX = ROOT / "src" / "layouts" / "_fixtures"
EXPECTED = {"cover_judul_raksasa", "cover_foto_judul_bawah", "penjelasan_teks_ikon", "penjelasan_split_foto",
            "daftar_bernomor", "data_angka_besar", "perbandingan_dua_kolom", "cta_komen"}


def test_batch1_is_complete_and_samples_are_valid() -> None:
    specs = registry.load_all()
    assert EXPECTED <= set(specs)
    for spec in specs.values():
        for name, s in spec.samples.items():
            errs = validate_content(spec, s["slots"], s.get("params"), s.get("emphasis"))
            assert errs == [], (spec.id, name, errs)


def test_emphasis_matches_whole_words_only() -> None:
    html = str(emph_html("pengamannya aman 35%", ["aman", "%"]))
    assert "pengamannya" in html and html.count('class="hl"') == 2
    assert '<em class="hl">%</em>' in html


def test_icons_and_list_rules() -> None:
    assert all("<svg" in str(icon_svg(n)) for n in ICON_NAMES)
    spec = registry.get("penjelasan_teks_ikon")
    assert any("ikon" in e for e in validate_content(spec, {"title": "Judul aman", "body": "x" * 30, "icon": "bukan_ikon"}))
    spec = registry.get("daftar_bernomor")
    errs = validate_content(spec, {"title": "Judul daftar", "points": ["satu", "dua"]})
    assert any("minimal 3" in e for e in errs)


def test_required_photo_is_enforced() -> None:
    spec = registry.get("cover_foto_judul_bawah")
    pack = build_pack(2, BRAND)
    s = spec.samples["typical"]
    with pytest.raises(Exception):
        render_layout_html(spec, s["slots"], s["params"], s["emphasis"], pack, 0, 5, BRAND, photo_url=None)


def test_every_layout_passes_automatic_gate(tmp_path: Path) -> None:
    try:
        renderer = Renderer().__enter__()
    except RenderError as exc:
        pytest.skip(str(exc))
    failures = []
    try:
        for spec in registry.load_all().values():
            variants = {"required": [True], "optional": [True, False], "none": [False]}[spec.meta.needs_photo]
            for seed, surface in ((2, "dark"), (1, "light")):
                pack = build_pack(seed, BRAND, 5, force_surface=surface)
                for set_name, sample in spec.samples.items():
                    for with_photo in variants:
                        photo = (FIX / f"{sample['photo']}.png").as_uri() if with_photo and sample.get("photo") else None
                        html = render_layout_html(spec, sample["slots"], sample.get("params", {}), sample.get("emphasis", []),
                                                  pack, 0 if spec.meta.role == "cover" else 2, 5, BRAND, photo_url=photo)
                        res = renderer.render(html, tmp_path / f"{spec.id}_{set_name}_{seed}_{with_photo}.jpg")
                        errors = [i for i in qc_dom.evaluate(res.report) if i.severity == "error"]
                        if errors or res.blocked:
                            failures.append((spec.id, set_name, surface, with_photo, [(i.code, i.element) for i in errors]))
    finally:
        renderer.__exit__(None, None, None)
    assert failures == []
