"""Renderer HTML: ukuran, laporan DOM, offline, dan helper teks."""
import json
from pathlib import Path

import pytest
from PIL import Image

from src.layouts import registry
from src.layouts.style.packs import build_pack
from src.render.assemble import balance_lines, emph_html, render_layout_html, title_lines
from src.render.renderer import RenderError, Renderer
from src.tools import qc_dom

BRAND = json.loads((Path(__file__).resolve().parents[1] / "config" / "brand.json").read_text(encoding="utf-8"))


def test_emphasis_is_escaped_and_wrapped() -> None:
    html = str(emph_html("<b>x</b> Aman kerja", ["aman"]))
    assert "&lt;b&gt;" in html and "<b>" not in html
    assert '<em class="hl">Aman</em>' in html


def test_balance_lines_is_balanced_and_bounded() -> None:
    words = "Cara Aman Memakai Mesin Press".split()
    groups = balance_lines(words, 3)
    assert len(groups) == 3 and sum(groups, []) == list(range(5))
    assert len(balance_lines(["Satu", "Dua"], 4)) == 2  # tidak lebih banyak dari jumlah kata
    assert len(title_lines("Hemat Listrik Pabrik Anda", 2)) == 2


def test_render_is_offline_sized_and_passes_qc(tmp_path: Path) -> None:
    spec = registry.get("cover_judul_raksasa")
    s = spec.samples["typical"]
    html = render_layout_html(spec, s["slots"], s["params"], s["emphasis"], build_pack(2, BRAND), 0, 5, BRAND)
    try:
        renderer = Renderer().__enter__()
    except RenderError as exc:
        pytest.skip(str(exc))
    try:
        res = renderer.render(html, tmp_path / "a.jpg")
        assert Image.open(res.path).size == (1080, 1350)
        assert res.blocked == []
        assert {"title#1", "kicker", "brand"} <= {i["id"] for i in res.report}
        assert qc_dom.passed(qc_dom.evaluate(res.report))
        bad = renderer.render('<html><body><img src="https://example.com/x.png"><script>window.__run=async()=>[]</script></body></html>',
                              tmp_path / "b.jpg")
        assert bad.blocked == ["https://example.com/x.png"]
    finally:
        renderer.__exit__(None, None, None)
