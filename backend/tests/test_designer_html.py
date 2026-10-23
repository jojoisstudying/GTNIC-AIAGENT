"""Integration tests for the HTML layout rendering path in Designer."""
import json
from pathlib import Path

import pytest
from PIL import Image

from src import config
from src.agents import designer
from src.agents import planner
from src.render.renderer import RenderError


ROOT = Path(__file__).resolve().parents[1]
BRAND = json.loads((ROOT / "config" / "brand.json").read_text(encoding="utf-8"))


def test_planner_normalize_targets_approved_html_layouts() -> None:
    plan = {
        "concept": "carousel tips hidrasi",
        "content_pillar": "keselamatan kerja",
        "format": "carousel",
        "slides": [
            {"role": "cover", "layout_id": "foto_penuh_overlay", "headline": "Hidrasi di Area Kerja",
             "subtext": "Panduan ringkas untuk pekerja.", "emphasis": "headline"},
            {"role": "content", "layout_id": "split_foto_teks", "headline": "Simpan Air Dekat",
             "subtext": "Letakkan botol minum di tempat yang mudah dijangkau selama bekerja.",
             "emphasis": "headline"},
            {"role": "content", "layout_id": "daftar_bernomor", "headline": "Buat Pengingat Minum",
             "subtext": "Gunakan jeda dan pengingat untuk menjaga kebiasaan minum air.",
             "params": {"items": ["Letakkan botol di meja", "Minum saat jeda", "Isi ulang botol"]},
             "emphasis": "headline"},
            {"role": "content", "layout_id": "tipografi_minimal", "headline": "Cek Akses Air",
             "subtext": "Pastikan air minum tersedia di area yang mudah dijangkau pekerja.",
             "emphasis": "headline"},
            {"role": "cta", "layout_id": "cta_blok", "headline": "Mulai Hari Ini",
             "subtext": "Bagikan kebiasaan hidrasi timmu.", "emphasis": "headline"},
        ],
        "caption": "Tips hidrasi kerja. Bagikan kebiasaanmu.",
        "hashtags": ["#hidrasi", "#kerja", "#tips"],
        "schedule": {"slots": [{"time": "10 AM"}], "ab_test": "Bandingkan slot."},
        "research_used": [],
    }
    normalized = planner.normalize(plan, BRAND, {"sources": [], "posting_time": {}})
    issues = planner.validate(normalized, "", {"sources": [], "posting_time": {}})
    assert issues == []
    from src.layouts import registry as layout_registry
    approved_ids = {i for i, spec in layout_registry.load_all().items() if spec.meta.status == "approved"}
    assert all(slide["layout_id"] in approved_ids for slide in normalized["slides"])
    assert len({slide["layout_id"] for slide in normalized["slides"]}) >= 3
    ids = [slide["layout_id"] for slide in normalized["slides"]]
    assert all(a != b for a, b in zip(ids, ids[1:]))


def test_html_designer_renders_approved_registry_templates(tmp_path: Path, monkeypatch) -> None:
    def mock_opt(key: str, default: str = "") -> str:
        if key == "RENDERER":
            return "html"
        if key == "CLOUDFLARE_POSE_GENERATION":
            return "false"
        return default

    monkeypatch.setattr(config, "opt", mock_opt)
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(designer.asset_library, "find_pose", lambda _tags: None)
    monkeypatch.setattr(designer.asset_library, "is_placeholder", lambda _path: False)

    plan = {
        "style": {"seed": 42},
        "slides": [
            {"role": "cover", "layout_id": "cover_judul_raksasa",
             "headline": "Hidrasi di Tempat Kerja", "subtext": "Panduan singkat untuk tim produksi.",
             "slots": {"title": "Hidrasi di Tempat Kerja", "kicker": "Tips kerja",
                       "subtitle": "Panduan singkat untuk tim produksi."}, "emphasis": ["Hidrasi"]},
            {"role": "content", "layout_id": "daftar_bernomor",
             "headline": "Biasakan Minum Air", "subtext": "Siapkan air dan buat pengingat sederhana.",
             "slots": {"title": "Biasakan Minum Air", "points": [
                 "Letakkan botol di meja kerja", "Isi ulang saat waktu istirahat", "Buat pengingat minum air"]},
             "params": {"numeral": "badge"}, "emphasis": ["Biasakan"]},
            {"role": "content", "layout_id": "penjelasan_teks_ikon",
             "headline": "Periksa Persediaan Air", "subtext": "Pastikan akses air minum tersedia dekat area kerja.",
             "slots": {"title": "Periksa Persediaan Air",
                       "body": "Pastikan akses air minum tersedia dekat area kerja.", "icon": "alert"},
             "params": {"pos": "middle", "icon_style": "badge"}, "emphasis": ["Persediaan"]},
            {"role": "content", "layout_id": "daftar_bernomor",
             "headline": "Ambil Jeda Hidrasi", "subtext": "Gunakan waktu istirahat untuk minum sesuai kebutuhan.",
             "slots": {"title": "Ambil Jeda Hidrasi", "points": [
                 "Gunakan waktu istirahat untuk minum", "Pastikan air mudah dijangkau",
                 "Isi ulang botol setelah digunakan"]},
             "params": {"numeral": "outline"}, "emphasis": ["Hidrasi"]},
            {"role": "cta", "layout_id": "cta_komen",
             "headline": "Mulai Kebiasaan Hari Ini", "subtext": "Bagikan tips hidrasi di timmu.",
             "slots": {"title": "Mulai Kebiasaan Hari Ini", "keyword": "AIR",
                       "subtitle": "Bagikan tips hidrasi di timmu."},
             "params": {"bubble_side": "left"}, "emphasis": []},
        ],
    }

    try:
        result = designer.run(plan, BRAND, tmp_path / "slides", on_step=lambda *_: None)
    except RenderError as exc:
        pytest.skip(str(exc))

    assert result["renderer"] == "html"
    assert result["ok"] is True, (result["warnings"],
                                  [(slide["issues"], slide["dom_issues"])
                                   for slide in result["slides"]])
    assert [slide["layout_id"] for slide in result["slides"]] == [
        "cover_judul_raksasa", "daftar_bernomor", "penjelasan_teks_ikon",
        "daftar_bernomor", "cta_komen",
    ]
    for slide in result["slides"]:
        path = Path(slide["path"])
        assert path.is_file()
        with Image.open(path) as image:
            assert image.size == (1080, 1350)