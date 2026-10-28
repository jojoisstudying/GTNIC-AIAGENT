"""Batch 2 (cover efek): sampel valid, gerbang 'teks tertutup subjek', dan variasi cover di planner."""
import json
from pathlib import Path

from src.carousel.agents import planner
from src.carousel.layouts import registry
from src.carousel.layouts.models import validate_content
from src.carousel.layouts.style.packs import build_pack
from src.carousel.render.assemble import render_layout_html
from src.carousel.render.renderer import Renderer
from src.carousel.tools import qc_dom

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "src" / "layouts" / "_fixtures"
BRAND = json.loads((ROOT / "config" / "brand.json").read_text(encoding="utf-8"))
BATCH2 = {"cover_teks_belakang_subjek", "cover_echo_blur", "cover_pose_lelucon",
          "cover_skala_objek", "cover_dialog_meme", "cover_pertanyaan_wajah_crop"}


def test_batch2_layouts_load_with_valid_samples() -> None:
    specs = {i: s for i, s in registry.load_all().items() if s.meta.batch == 2}
    assert set(specs) == BATCH2
    for s in specs.values():
        assert s.meta.role == "cover" and s.meta.needs_photo == "required"
        for name, sm in s.samples.items():
            assert validate_content(s, sm["slots"], sm.get("params"), sm.get("emphasis")) == [], (s.id, name)


def _item(**kw) -> dict:
    base = {"id": "title#1", "kind": "text", "slot": "title", "bbox": {"x": 64, "y": 215, "w": 900, "h": 150},
            "fits": True, "min_font": 72, "font_px": 120, "bleed": False, "contrast_min": 9.0}
    return {**base, **kw}


def test_qc_rejects_text_mostly_hidden_behind_subject() -> None:
    assert not [i for i in qc_dom.evaluate([_item(behind=True, occlusion=0.2)]) if i.severity == "error"]
    bad = [i for i in qc_dom.evaluate([_item(behind=True, occlusion=0.5)]) if i.severity == "error"]
    assert [i.code for i in bad] == ["teks_tertutup_subjek"]
    # elemen biasa (bukan data-behind) tidak punya 'occlusion' sehingga aturan ini tidak berlaku
    assert not [i for i in qc_dom.evaluate([_item()]) if i.severity == "error"]


def _render(spec, sn: str, ph: int | None = None):
    sm = spec.samples[sn]
    pack = build_pack(2, BRAND, 5, force_surface="dark")
    html = render_layout_html(spec, sm["slots"], sm.get("params", {}), sm.get("emphasis", []), pack, 0, 5, BRAND,
                              photo_url=(FIX / f"{sm['photo']}.png").as_uri())
    if ph:
        html = html.replace("--ph:905px", f"--ph:{ph}px")
    with Renderer() as r:
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            return r.render(html, Path(d) / "o.jpg")


def test_text_behind_subject_is_measured_and_gated_in_a_real_render() -> None:
    spec = registry.load_all()["cover_teks_belakang_subjek"]
    ok = _render(spec, "typical")
    occ = [it["occlusion"] for it in ok.report if it.get("behind")]
    assert occ and max(occ) <= qc_dom.MAX_OCCLUSION
    assert not [i for i in qc_dom.evaluate(ok.report) if i.severity == "error"]
    # subjek diperbesar sampai menutupi judul -> gerbang harus menolak
    big = _render(spec, "min", ph=1350)
    assert "teks_tertutup_subjek" in {i.code for i in qc_dom.evaluate(big.report)}


def _lazy(i: int) -> dict:
    return {"concept": f"post {chr(65 + i)}", "content_pillar": BRAND["content_pillars"][0], "format": "carousel", "slides": [
        {"role": "cover", "layout_id": "cover_foto_judul_bawah", "headline": "Cek Alat Dulu", "subtext": "Untuk seluruh tim.", "pose_tags": ["senyum"]},
        {"role": "content", "layout_id": "penjelasan_teks_ikon", "headline": "Kenali Dasar Kerja", "subtext": "Pahami prinsip kerja sebelum mulai bekerja di lokasi agar tenang."},
        {"role": "content", "layout_id": "daftar_bernomor", "headline": "Tiga Langkah Mudah", "subtext": "Siapkan alat. Periksa area. Catat hasil.", "params": {"items": ["Siapkan alat", "Periksa area", "Catat hasil"]}},
        {"role": "content", "layout_id": "penjelasan_split_foto", "headline": "Biasakan Setiap Hari", "subtext": "Kebiasaan kecil yang rutin memberi dampak besar bagi seluruh tim."},
        {"role": "cta", "layout_id": "cta_komen", "headline": "Tertarik Mencoba?", "subtext": "Tulis pertanyaanmu di komentar."}],
        "caption": "c", "hashtags": ["#a", "#b", "#c"], "schedule": {"slots": [{"time": "10 AM"}], "ab_test": "x"}, "research_used": []}


def test_planner_rotates_among_many_cover_layouts() -> None:
    specs = registry.load_all()
    history, covers = [], []
    for i in range(12):
        plan = planner.normalize(_lazy(i), BRAND, {"sources": [], "posting_time": {}}, history=history, approved=specs)
        issues = [m for m in planner.validate(plan, "", {"sources": [], "posting_time": {}}, history=history, approved=specs)
                  if not any(k in m for k in ("caption", "hashtag", "schedule"))]
        assert issues == [], issues
        covers.append(plan["slides"][0]["layout_id"])
        history = [planner.summarize_plan(plan)] + history[:5]
    assert all(a != b for a, b in zip(covers, covers[1:]))
    assert len(set(covers)) >= 4 and set(covers) & BATCH2
