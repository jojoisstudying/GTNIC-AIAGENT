"""Tests for Carousel-level Semantic QC and Pillow renderer metadata (BUG-05, BUG-08)."""
import pytest
from src.carousel.tools.semantic_qc import check_carousel_semantics
from src.carousel.agents import designer
from src import config


def test_semantic_qc_detects_duplicate_headlines():
    plan = {
        "slides": [
            {"role": "cover", "headline": "Judul Cover"},
            {"role": "content", "headline": "Tips Efisiensi Sistem"},
            {"role": "content", "headline": "Tips Efisiensi Sistem"},  # duplicate
            {"role": "cta", "headline": "Bagikan Sekarang"}
        ]
    }
    result = check_carousel_semantics(plan)
    errors = result["errors"]
    assert any("pengulangan" in e for e in errors)
    assert not result["ok"]


def test_semantic_qc_validates_role_order():
    # first slide not cover
    bad_plan = {
        "slides": [
            {"role": "content", "headline": "Bukan Cover"},
            {"role": "cta", "headline": "CTA"}
        ]
    }
    result = check_carousel_semantics(bad_plan)
    errors = result["errors"]
    assert any("cover" in e for e in errors)
    assert any("di antara 3 hingga 10" in e for e in errors)


def test_semantic_qc_returns_structured_ok_result_and_nonblocking_warnings():
    plan = {"slides": [
        {"role": "cover", "headline": "Cover"},
        {"role": "content", "headline": "Isi"},
        {"role": "content", "headline": "Detail"},
    ]}
    result = check_carousel_semantics(plan)
    assert result["ok"] is True
    assert result["errors"] == []
    assert result["warnings"]
    assert result["checks"]["slide_count"] is True


def test_semantic_qc_blocks_irrelevant_content_and_brand_violation():
    plan = {"slides": [
        {"role": "cover", "headline": "Klaim 99%"},
        {"role": "content", "headline": "Riset"},
        {"role": "cta", "headline": "Maintenance"},
    ]}
    result = check_carousel_semantics(plan, {"facts": {"stats": []}},
                                      {"rules": {"forbidden_terms": ["MAINTENANCE"]}}, topic="Resep Rendang")
    assert result["ok"] is False
    assert result["checks"]["topic_relevance"] is False
    assert result["checks"]["brand_consistency"] is False


def test_semantic_qc_accepts_relevant_topic():
    plan = {"concept": "Checklist maintenance website untuk keamanan digital", "slides": [
        {"role": "cover", "headline": "Maintenance Website"},
        {"role": "content", "headline": "Keamanan Digital"},
        {"role": "cta", "headline": "Diskusikan"},
    ]}
    result = check_carousel_semantics(plan, topic="Maintenance Website")
    assert result["ok"] is True
    assert result["checks"]["topic_relevance"] is True


def test_pillow_renderer_metadata_initialized(tmp_path, monkeypatch):
    """Verifies that RENDERER=pillow initializes consistent metadata schema (BUG-05)."""
    monkeypatch.setattr(config, "opt", lambda k, d="": "pillow" if k == "RENDERER" else d)
    plan = {
        "slides": [
            {"role": "cover", "layout_id": "angka_besar", "headline": "100%", "subtext": "Uptime"},
            {"role": "content", "layout_id": "tipografi_minimal", "headline": "Aman", "subtext": "Sistem andal"},
            {"role": "cta", "layout_id": "cta_blok", "headline": "Hubungi Kami", "subtext": "Sekarang"}
        ]
    }
    brand = {
        "colors": {"primary": "#0f172a", "secondary": "#f8fafc", "accent": "#38bdf8", "text_on_primary": "#ffffff"},
        "tokens": {"bg": "#0f172a", "light_bg": "#f8fafc", "fg": "#ffffff", "accent": "#38bdf8"},
        "fonts": {"display": {"family": "DejaVu Sans", "file": "DejaVuSans-Bold.ttf", "weight": 700},
                  "body": {"family": "DejaVu Sans", "file": "DejaVuSans.ttf", "weight": 400},
                  "medium": {"family": "DejaVu Sans", "file": "DejaVuSans.ttf", "weight": 500}},
        "chrome": {"brand_text": "Resilience", "header": False, "page_counter": False, "footer": {"show": False}, "swipe_hint": False}
    }
    result = designer.run(plan, brand, tmp_path / "slides", on_step=lambda *_: None)
    for s in result["slides"]:
        assert "issues" in s
        assert "dom_issues" in s
        assert "path" in s
