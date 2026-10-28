"""Tests for Fase 2 parametric layouts and visual rhythm validation."""
import json
from pathlib import Path
import pytest
from PIL import Image

from src.carousel.layouts import (
    LAYOUT_REGISTRY,
    VALID_LAYOUT_IDS,
    get_layout_renderer,
    validate_rhythm,
)


@pytest.fixture
def dummy_brand():
    return {
        "company": "Test Industri",
        "colors": {
            "primary": "#0B2A5B",
            "secondary": "#EAF1FF",
            "accent": "#FFB400",
            "text_on_primary": "#FFFFFF"
        },
        "font_path": "assets/fonts/DejaVuSans-Bold.ttf",
        "font_regular_path": "assets/fonts/DejaVuSans.ttf",
    }


def test_all_initial_layouts_registered():
    expected = [
        "angka_besar",
        "split_foto_teks",
        "foto_penuh_overlay",
        "kutipan",
        "daftar_bernomor",
        "perbandingan",
        "tipografi_minimal",
        "langkah_diagram",
        "cta_blok",
    ]
    for lid in expected:
        assert lid in VALID_LAYOUT_IDS
        renderer = get_layout_renderer(lid)
        assert callable(renderer)


def test_render_each_layout(dummy_brand, tmp_path):
    text = {"headline": "Inovasi Produksi Modern", "subtext": "Meningkatkan ketepatan dan efisiensi kerja tim secara konsisten setiap hari."}
    for lid in VALID_LAYOUT_IDS:
        renderer = get_layout_renderer(lid)
        out_file = tmp_path / f"test_{lid}.jpg"
        meta = renderer(
            text=text,
            photo_path=None,
            brand=dummy_brand,
            params={"number": "95%", "label": "Efisiensi", "author": "CEO Test"},
            out_path=out_file
        )
        assert out_file.is_file()
        assert meta["layout_id"] == lid
        assert meta["overflow"] is False
        with Image.open(out_file) as im:
            assert im.size == (1080, 1350)


def test_validate_rhythm_rules():
    # 1. Reject identical consecutive layouts
    slides_consecutive = [
        {"role": "cover", "layout_id": "split_foto_teks"},
        {"role": "content", "layout_id": "angka_besar"},
        {"role": "content", "layout_id": "angka_besar"}, # duplicate consecutive
        {"role": "content", "layout_id": "daftar_bernomor"},
        {"role": "cta", "layout_id": "cta_blok"},
    ]
    issues = validate_rhythm(slides_consecutive)
    assert any("berulang berurutan" in iss for iss in issues)

    # 2. Reject cover same as body
    slides_cover_same = [
        {"role": "cover", "layout_id": "split_foto_teks"},
        {"role": "content", "layout_id": "angka_besar"},
        {"role": "content", "layout_id": "split_foto_teks"}, # same as cover
        {"role": "content", "layout_id": "daftar_bernomor"},
        {"role": "cta", "layout_id": "cta_blok"},
    ]
    issues = validate_rhythm(slides_cover_same)
    assert any("cover memakai layout" in iss for iss in issues)

    # 3. Reject fewer than 3 distinct layouts
    slides_few_distinct = [
        {"role": "cover", "layout_id": "split_foto_teks"},
        {"role": "content", "layout_id": "cta_blok"},
        {"role": "content", "layout_id": "cta_blok"}, # also consecutive
        {"role": "cta", "layout_id": "split_foto_teks"},
    ]
    issues = validate_rhythm(slides_few_distinct)
    assert any("minimal 3 layout berbeda" in iss for iss in issues)

    # 4. Valid rhythm passes without issues
    slides_valid = [
        {"role": "cover", "layout_id": "foto_penuh_overlay"},
        {"role": "content", "layout_id": "angka_besar"},
        {"role": "content", "layout_id": "daftar_bernomor"},
        {"role": "content", "layout_id": "langkah_diagram"},
        {"role": "cta", "layout_id": "cta_blok"},
    ]
    assert validate_rhythm(slides_valid) == []
