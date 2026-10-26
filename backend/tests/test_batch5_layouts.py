"""Batch 5 (CTA): sampel valid, tanpa tombol palsu, dan pemilihan CTA yang selaras dengan ajakan teks."""
import json
from pathlib import Path

from src.agents import planner
from src.layouts import registry
from src.layouts.models import validate_content
from src.render.assemble import emph_html

ROOT = Path(__file__).resolve().parents[1]
BRAND = json.loads((ROOT / "config" / "brand.json").read_text(encoding="utf-8"))
RESEARCH = {"sources": [], "posting_time": {}}
BATCH5 = {"cta_simpan_bagikan", "cta_foto_ajakan", "cta_pertanyaan_komen", "cta_teks_besar"}
# Aturan CTA dokumen: hanya aksi native IG; dilarang tombol palsu yang tak bisa diklik di gambar carousel.
FORBIDDEN = ("klik", "lihat selengkapnya", "link di bio", "tap di sini", "click", "swipe up")


def test_batch5_layouts_load_with_valid_samples_and_library_is_complete() -> None:
    specs = registry.load_all()
    assert len(specs) == 30
    new = {i: s for i, s in specs.items() if s.meta.batch == 5}
    assert set(new) == BATCH5
    for s in new.values():
        assert s.meta.role == "cta"
        for name, sm in s.samples.items():
            assert validate_content(s, sm["slots"], sm.get("params"), sm.get("emphasis")) == [], (s.id, name)


def test_cta_layouts_have_no_fake_buttons() -> None:
    for s in registry.load_all().values():
        if s.meta.role != "cta":
            continue
        html = (ROOT / "src" / "layouts" / s.id / "layout.html").read_text(encoding="utf-8").lower()
        samples = json.dumps(s.samples, ensure_ascii=False).lower()
        for word in FORBIDDEN:
            assert word not in html and word not in samples, (s.id, word)


def _plan(i: int, cta_text: str) -> dict:
    return {"concept": f"tes {i}", "content_pillar": BRAND["content_pillars"][0], "format": "carousel", "slides": [
        {"role": "cover", "layout_id": "cover_foto_judul_bawah", "headline": "Cek Alat Dulu", "subtext": "Untuk seluruh tim.", "pose_tags": ["senyum"]},
        {"role": "content", "layout_id": "penjelasan_teks_ikon", "headline": "Kenali Dasar Kerja", "subtext": "Pahami prinsip kerja sebelum mulai bekerja di lokasi agar tenang."},
        {"role": "content", "layout_id": "daftar_bernomor", "headline": "Tiga Langkah Mudah", "subtext": "Siapkan alat. Periksa area. Catat hasil.", "params": {"items": ["Siapkan alat", "Periksa area", "Catat hasil"]}},
        {"role": "content", "layout_id": "penjelasan_split_foto", "headline": "Biasakan Setiap Hari", "subtext": "Kebiasaan kecil yang rutin memberi dampak besar bagi seluruh tim."},
        {"role": "cta", "layout_id": "cta_komen", "headline": "Tertarik Mencoba?", "subtext": cta_text}],
        "caption": "c", "hashtags": ["#a", "#b", "#c"], "schedule": {"slots": [{"time": "10 AM"}], "ab_test": "x"}, "research_used": []}


def _ctas(cta_text: str, n: int = 12) -> list[str]:
    specs, history, out = registry.load_all(), [], []
    for i in range(n):
        plan = planner.normalize(_plan(i, cta_text), BRAND, RESEARCH, history=history, approved=specs)
        out.append(plan["slides"][-1]["layout_id"])
        history = [planner.summarize_plan(plan)] + history[:5]
    return out


def test_planner_never_picks_a_cta_that_contradicts_the_text() -> None:
    comment = _ctas("Tulis pertanyaanmu di komentar.")
    assert "cta_simpan_bagikan" not in comment and len(set(comment)) >= 3
    save_share = _ctas("Simpan dan bagikan ke rekan satu timmu.")
    assert not {"cta_komen", "cta_pertanyaan_komen"} & set(save_share) and "cta_simpan_bagikan" in save_share
    follow = _ctas("Ikuti kami untuk tips lainnya.")
    assert not {"cta_komen", "cta_pertanyaan_komen", "cta_simpan_bagikan"} & set(follow)


def test_cta_rotates_between_posts_when_alternatives_exist() -> None:
    seq = _ctas("Tulis pertanyaanmu di komentar.", 14)
    assert all(a != b for a, b in zip(seq, seq[1:]))


def test_emphasis_marks_only_the_first_occurrence_of_a_phrase() -> None:
    assert str(emph_html("Kami baca dan balas satu per satu.", ["satu"])).count('class="hl"') == 1
