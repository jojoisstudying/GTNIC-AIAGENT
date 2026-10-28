"""Aksen hemat di renderer + variasi & anti-ulang di planner (tanpa LLM, tanpa jaringan)."""
import json
import random
from pathlib import Path

from src.carousel.agents import planner
from src.carousel.layouts.style.packs import build_pack
from src.carousel.render.assemble import emph_html, title_lines

BRAND = json.loads((Path(__file__).resolve().parents[1] / "config" / "brand.json").read_text(encoding="utf-8"))
RESEARCH = {"sources": [], "posting_time": {}, "facts": {"stats": []}}


def test_whole_title_emphasis_is_ignored() -> None:
    html = str(emph_html("Cara Magang di Industri Dummy", ["Cara Magang di Industri Dummy"]))
    assert 'class="hl"' not in html


def test_consecutive_marked_words_share_one_box() -> None:
    line = str(title_lines("Tertarik Magang Industri Dummy", 1, ["Magang Industri"])[0])
    assert line.count('class="hl"') == 1 and "Magang Industri</em>" in line


def test_emphasis_is_capped_to_two_phrases() -> None:
    html = str(emph_html("satu dua tiga empat lima", ["dua", "tiga", "empat"]))
    assert html.count('class="hl"') == 2


def test_accent_shape_is_an_outline_not_a_muddy_fill() -> None:
    for seed in range(60):
        pack = build_pack(seed, BRAND, total=5)
        from src.carousel.layouts.style.packs import deco_html
        svg = deco_html(pack, 0)
        if any(s["tone"] == "accent" for s in pack["shapes"]):
            assert 'fill="none"' in svg and "stroke-width=\"5\"" in svg
            return
    raise AssertionError("tidak ada pack beraksen dalam 60 seed")


def _lazy_plan(i: int) -> dict:
    return {"concept": f"post {chr(65 + i % 26)}", "content_pillar": BRAND["content_pillars"][0], "format": "carousel",
            "slides": [
                {"role": "cover", "layout_id": "cover_foto_judul_bawah", "headline": "Judul Cover Utama", "subtext": "Panduan singkat untuk tim.", "pose_tags": ["senyum"]},
                {"role": "content", "layout_id": "penjelasan_split_foto", "headline": "Kenali Lingkungan Kerja", "subtext": "Pelajari proses dan peralatan sebelum mulai bekerja di lokasi.", "pose_tags": ["menunjuk"]},
                {"role": "content", "layout_id": "daftar_bernomor", "headline": "Tiga Langkah Mudah", "subtext": "Siapkan CV. Kirim lamaran. Latih wawancara.", "params": {"items": ["Siapkan CV terbaru", "Kirim lamaran resmi", "Latih pertanyaan umum"]}},
                {"role": "content", "layout_id": "penjelasan_teks_ikon", "headline": "Tunjukkan Kemampuan", "subtext": "Buat prototipe sederhana dan unggah ke portofolio kamu.", "slots": {"icon": "alert"}},
                {"role": "cta", "layout_id": "cta_komen", "headline": "Tertarik Bergabung?", "subtext": "Tulis pertanyaanmu di komentar.", "slots": {"keyword": "BAGIKAN", "verb": "bagikan"}}],
            "caption": "c", "hashtags": ["#a", "#b", "#c"], "schedule": {"slots": [{"time": "10 AM"}], "ab_test": "x"}, "research_used": []}


def test_planner_enforces_variety_over_a_lazy_llm() -> None:
    history, covers = [], []
    for i in range(12):
        plan = planner.normalize(_lazy_plan(i), BRAND, RESEARCH, history=history)
        ids = [s["layout_id"] for s in plan["slides"]]
        assert all(a != b for a, b in zip(ids, ids[1:]))                      # tidak ada layout berulang berurutan
        assert 1 <= sum(bool(s["pose_tags"]) for s in plan["slides"]) <= 2    # kuota foto
        assert plan["slides"][-1]["slots"]["verb"] == "komen"                 # CTA konsisten dengan komentar
        assert plan["slides"][3]["slots"].get("icon") != "alert"              # ikon tanpa alasan diganti
        assert all(len(s["emphasis"]) <= 2 for s in plan["slides"])
        issues = [m for m in planner.validate(plan, "", RESEARCH, history=history)
                  if not any(k in m for k in ("caption", "hashtag", "schedule"))]
        assert issues == [], issues
        covers.append(ids[0])
        history = [planner.summarize_plan(plan)] + history[:5]
    assert all(a != b for a, b in zip(covers, covers[1:]))                    # cover bergantian antar post


# ------------------------------------------------------------------ batch 3-4 + kejujuran data

def test_batch34_layouts_load_with_valid_samples() -> None:
    from src.carousel.layouts import registry
    from src.carousel.layouts.models import validate_content
    new = [s for s in registry.load_all().values() if s.meta.batch in (3, 4)]
    assert len(new) == 12
    for s in new:
        for name, sm in s.samples.items():
            assert validate_content(s, sm["slots"], sm.get("params"), sm.get("emphasis")) == [], (s.id, name)


_NEEDS_DATA = {"bukti_kutipan", "data_tiga_angka", "data_angka_besar",
               "perbandingan_mitos_fakta", "perbandingan_sebelum_sesudah"}


def test_planner_never_fabricates_quotes_stats_or_comparisons() -> None:
    from src.carousel.layouts import registry
    specs = registry.load_all()           # termasuk layout draft: uji aturan, bukan status
    for i in range(10):
        plan = planner.normalize(_lazy_plan(i), BRAND, RESEARCH, approved=specs)
        assert not {s["layout_id"] for s in plan["slides"]} & _NEEDS_DATA


def test_planner_uses_sourced_facts_exactly() -> None:
    from src.carousel.layouts import registry
    specs = registry.load_all()
    stats = [{"value": "72%", "label": "Peserta merasa lebih percaya diri", "source": "Survei internal"},
             {"value": "3x", "label": "Latihan dalam sebulan", "source": "Survei internal"},
             {"value": "95%", "label": "Hadir sampai selesai", "source": "Laporan program"}]
    quote = {"text": "Pendampingan dari tim senior membuat saya cepat memahami alur kerja di pabrik.",
             "name": "Dimas Pratama", "source": "Operator shift pagi"}
    research = {"sources": [], "posting_time": {}, "facts": {"stats": stats, "quotes": [quote]}}
    seen = set()
    history = []
    for i in range(12):
        plan = planner.normalize(_lazy_plan(i), BRAND, research, history=history, approved=specs)
        issues = [m for m in planner.validate(plan, "", research, history=history, approved=specs)
                  if not any(k in m for k in ("caption", "hashtag", "schedule"))]
        assert issues == [], issues
        for s in plan["slides"]:
            if s["layout_id"] == "data_tiga_angka":
                assert {s["slots"][f"value_{k}"] for k in (1, 2, 3)} == {"72%", "3x", "95%"}
            if s["layout_id"] == "bukti_kutipan":
                assert s["slots"]["quote"] == quote["text"] and s["slots"]["name"] == quote["name"]
            seen.add(s["layout_id"])
        history = [planner.summarize_plan(plan)] + history[:5]
    assert seen & {"bukti_kutipan", "data_tiga_angka", "data_angka_besar"}   # data layout terpakai bila ada fakta


def test_planner_fills_generic_list_steps_and_numbers() -> None:
    from src.carousel.layouts import registry
    specs = registry.load_all()
    only = {k: specs[k] for k in ("cover_judul_raksasa", "langkah_timeline", "langkah_nomor_besar", "cta_komen")}
    plan = _lazy_plan(0)
    plan["slides"][2]["params"] = {"items": ["Siapkan alat", "Periksa area", "Catat hasil"]}
    out = planner.normalize(plan, BRAND, RESEARCH, approved=only)
    by_id = {s["layout_id"]: s for s in out["slides"]}
    if "langkah_timeline" in by_id:
        assert len(by_id["langkah_timeline"]["slots"]["steps"]) >= 3
    if "langkah_nomor_besar" in by_id:
        assert by_id["langkah_nomor_besar"]["slots"]["number"].isdigit()
