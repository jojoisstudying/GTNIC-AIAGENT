"""facts.stats / facts.quotes: angka & kutipan hanya dari fakta pemilik atau ekstraksi KODE yang verbatim."""
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

from src.carousel.agents import facts

SNIPPET = (
    "Short-form video tips for marketers. Teams that plan content weekly see 38% more consistent posting than "
    "teams that do not. \u201cConsistency beats intensity when you build an audience,\u201d said Maria Santos, head of "
    "community at Later. Up to 90% of brands test posting times. In 2025, brands posted 3x more Reels."
)


def _gathered(content: str = SNIPPET, published: str = "2026-03-01") -> list:
    return [{"tool": "search_social_trends", "args": {}, "result": {"results": [
        {"title": "t", "url": "https://www.later.com/blog/x", "published": published, "content": content}]}}]


# ------------------------------------------------------------------ ekstraksi kode

def test_candidate_stats_are_verbatim_and_skip_qualified_numbers() -> None:
    cands = facts.candidate_stats(_gathered())
    values = [c["value"] for c in cands]
    assert "38%" in values and "3x" in values
    assert "90%" not in values                       # "Up to 90%": pembatas mengubah makna, dibuang
    assert not any(v in ("2025",) for v in values)   # tahun bukan statistik
    for c in cands:
        assert c["value"] in c["sentence"]           # nilai = teks persis di sumber
        assert c["source"] == "Later (2026)"


def test_candidate_quotes_are_verbatim_with_named_attribution() -> None:
    quotes = facts.candidate_quotes(_gathered())
    assert len(quotes) == 1
    q = quotes[0]
    assert q["text"] == "Consistency beats intensity when you build an audience"
    assert q["name"] == "Maria Santos" and q["source"] == "head of community at Later"


def test_candidate_quotes_reject_unnamed_or_short_quotes() -> None:
    text = ('"Too short," said Dan Lee, a coach. "This quote is long enough but nobody is named" and so on. '
            '"According to the report this long sentence should not count as a person quote," said According Report.')
    assert facts.candidate_quotes(_gathered(text)) == []


def test_candidate_quotes_support_attribution_before_quote() -> None:
    text = 'Jane Roe, founder of Acme, said: "Small habits repeated every single day create the biggest results."'
    q = facts.candidate_quotes(_gathered(text))
    assert q and q[0]["name"] == "Jane Roe" and q[0]["text"].startswith("Small habits")


# ------------------------------------------------------------------ penilaian model: nilai tidak pernah dari model

def test_judgement_never_changes_value_or_evidence() -> None:
    stats, quotes = facts.candidate_stats(_gathered()), facts.candidate_quotes(_gathered())
    sid = next(c["id"] for c in stats if c["value"] == "38%")
    judged = {"stats": [{"id": sid, "keep": True, "label": "Posting konsisten dengan rencana mingguan", "value": "99%",
                         "evidence": "karangan"}, {"id": 99, "keep": True, "label": "Tidak ada kandidat ini"}],
              "quotes": [{"id": 0, "keep": True, "text": "kutipan karangan"}]}
    out_s, out_q, _ = facts.apply_judgement(stats, quotes, judged)
    assert [s["value"] for s in out_s] == ["38%"]
    assert "karangan" not in json.dumps(out_s, ensure_ascii=False)
    assert out_q[0]["text"] == "Consistency beats intensity when you build an audience"


def test_judgement_rejects_labels_with_digits_or_bad_length() -> None:
    stats = facts.candidate_stats(_gathered())
    sid = stats[0]["id"]
    for bad in ("Naik 38% dalam sebulan penuh", "pendek", "x" * 60):
        out_s, _, warnings = facts.apply_judgement(stats, [], {"stats": [{"id": sid, "keep": True, "label": bad}]})
        assert out_s == [] and warnings


def test_extract_fails_closed_when_model_is_unavailable_or_invalid() -> None:
    def boom(system, user):
        raise RuntimeError("model mati")
    s, q, w = facts.extract_web_facts("topik", _gathered(), boom)
    assert s == [] and q == [] and w
    s, q, w = facts.extract_web_facts("topik", _gathered(), lambda system, user: "bukan json")
    assert s == [] and q == [] and w


def test_no_model_call_when_there_are_no_candidates() -> None:
    def never(system, user):
        raise AssertionError("tidak boleh dipanggil tanpa kandidat")
    assert facts.extract_web_facts("topik", _gathered("Tidak ada angka di sini sama sekali."), never) == ([], [], [])


# ------------------------------------------------------------------ fakta pemilik

def test_brand_facts_are_validated_for_shape_only() -> None:
    raw = {"stats": [{"value": "120", "label": "Peserta magang tahun lalu", "source": "Data HRD 2025"},
                     {"value": "1234567", "label": "Terlalu panjang nilainya", "source": "HRD"},
                     {"value": "5", "label": "pendek", "source": "HRD"}, "bukan objek"],
           "quotes": [{"text": "Pendampingan tim senior membuat saya cepat memahami alur kerja di pabrik.",
                       "name": "Dimas Pratama", "source": "Operator shift pagi"},
                      {"text": "terlalu pendek", "name": "Siti", "source": ""}]}
    cleaned, warnings = facts.clean_brand_facts(raw)
    assert [s["value"] for s in cleaned["stats"]] == ["120"] and len(cleaned["quotes"]) == 1
    assert len(warnings) == 4 and all(i["origin"] == "brand" for i in cleaned["stats"] + cleaned["quotes"])
    assert facts.clean_brand_facts(None) == ({"stats": [], "quotes": []}, [])


def test_build_facts_puts_brand_first_and_deduplicates() -> None:
    brand = {"stats": [{"value": "38%", "label": "Posting konsisten dengan rencana mingguan", "source": "Data internal"}]}
    ask = lambda system, user: json.dumps({"stats": [{"id": 0, "keep": True, "label": "Posting konsisten dengan rencana mingguan"}],
                                           "quotes": [{"id": 0, "keep": True}]})
    out, _ = facts.build_facts("topik", _gathered(), brand, ask)
    assert out["stats"][0]["origin"] == "brand" and len(out["stats"]) == 1      # duplikat web dibuang
    assert out["quotes"][0]["origin"] == "web" and out["quotes"][0]["name"] == "Maria Santos"


# ------------------------------------------------------------------ integrasi run(): LLM tidak bisa menyuntik fakta

def test_run_builds_facts_in_code_and_strips_model_injected_facts() -> None:
    from src import config
    from src.carousel.agents import research_agent as ra
    judge_calls = []
    final = {"trending_formats": [{"name": "Carousel", "why": "format yang mudah disimpan", "source_url": "https://later.com/blog/x"}],
             "content_angles": ["Rutinitas singkat tim"], "posting_time": {"instagram": "x", "tiktok": "y", "basis": "global",
             "needs_testing": True, "caveats": "", "source_urls": []}, "lessons_from_past_posts": "", "sources": ["https://later.com/blog/x"],
             "facts": {"stats": [{"value": "99%", "label": "Angka karangan model", "source": "x"}], "quotes": []}}

    def create(**kw):
        msgs = kw["messages"]
        if "tools" in kw:
            i = sum(1 for m in msgs if m["role"] == "tool")
            if i == 0:
                tc = NS(id="c0", function=NS(name="search_social_trends", arguments='{"query":"q"}'))
                return NS(choices=[NS(message=NS(content=None, tool_calls=[tc]))])
            return NS(choices=[NS(message=NS(content=json.dumps(final), tool_calls=None))])
        if msgs[0]["content"].startswith("Kamu pemeriksa kandidat fakta"):
            judge_calls.append(msgs[1]["content"])
            return NS(choices=[NS(message=NS(content=json.dumps({"stats": [{"id": 0, "keep": True,
                      "label": "Posting konsisten dengan rencana mingguan"}], "quotes": [{"id": 0, "keep": True}]}), tool_calls=None))])
        raise AssertionError("panggilan tak terduga")

    saved = (dict(ra.TOOL_IMPL), config.OUTPUT_DIR)
    ra.TOOL_IMPL["search_social_trends"] = lambda query: _gathered()[0]["result"]
    ra.TOOL_IMPL["get_my_recent_performance"] = lambda: {"posts": [], "post_count": 0, "enough_data": False}
    brand_facts = {"stats": [{"value": "120", "label": "Peserta magang tahun lalu", "source": "Data HRD 2025"}]}
    try:
        with tempfile.TemporaryDirectory() as d:
            config.OUTPUT_DIR = Path(d)
            out = ra.run("tes", "tes", client=NS(chat=NS(completions=NS(create=create))), on_step=lambda m: None,
                         brand_facts=brand_facts)
    finally:
        ra.TOOL_IMPL.clear(); ra.TOOL_IMPL.update(saved[0]); config.OUTPUT_DIR = saved[1]
    f = out["data"]["facts"]
    assert "99%" not in json.dumps(f) and "karangan" not in json.dumps(f)           # suntikan model dibuang
    assert [s["value"] for s in f["stats"]] == ["120", "38%"]                       # pemilik dulu, lalu web
    assert f["stats"][1]["evidence"].startswith("Teams that plan content weekly")
    assert f["stats"][1]["source"] == "Later (2026)" and f["quotes"][0]["name"] == "Maria Santos"
    assert len(judge_calls) == 1


def test_run_never_keeps_model_facts_even_if_fact_building_crashes() -> None:
    from src import config
    from src.carousel.agents import research_agent as ra
    final = {"trending_formats": [], "content_angles": ["Rutinitas singkat tim"], "posting_time": {"instagram": "x", "tiktok": "y",
             "basis": "global", "needs_testing": True, "caveats": "", "source_urls": []}, "lessons_from_past_posts": "",
             "sources": ["https://later.com/blog/x"], "facts": {"stats": [{"value": "99%", "label": "Angka karangan model", "source": "x"}]}}

    def create(**kw):
        if "tools" in kw:
            return NS(choices=[NS(message=NS(content=json.dumps(final), tool_calls=None))])
        raise AssertionError("panggilan tak terduga")

    def crash(*a, **k):
        raise RuntimeError("bug di pembangun fakta")

    saved = (dict(ra.TOOL_IMPL), config.OUTPUT_DIR, ra.facts_mod.build_facts)
    ra.TOOL_IMPL["get_my_recent_performance"] = lambda: {"posts": [], "post_count": 0, "enough_data": False}
    ra.facts_mod.build_facts = crash
    try:
        with tempfile.TemporaryDirectory() as d:
            config.OUTPUT_DIR = Path(d)
            out = ra.run("tes", "tes", client=NS(chat=NS(completions=NS(create=create))), on_step=lambda m: None)
    finally:
        ra.TOOL_IMPL.clear(); ra.TOOL_IMPL.update(saved[0]); config.OUTPUT_DIR = saved[1]; ra.facts_mod.build_facts = saved[2]
    assert out["ok"] and out["data"]["facts"] == {"stats": [], "quotes": []}
    assert any("facts gagal" in w for w in out["warnings"])


def test_planner_can_use_built_facts_exactly() -> None:
    from src.carousel.agents import planner
    from src.carousel.layouts import registry
    from src.carousel.layouts.models import validate_content
    research = {"facts": {"stats": [{"value": "38%", "label": "Posting konsisten dengan rencana mingguan",
                                     "source": "Later (2026)", "origin": "web"}], "quotes": []}}
    spec = registry.load_all()["data_angka_besar"]
    slide = {"role": "content", "headline": "Rencana Mingguan Bantu Konsisten", "subtext": "Konten yang direncanakan lebih mudah dijaga.",
             "slots": {}, "params": {}}
    planner._complete_layout_content(slide, spec, research)
    assert slide["slots"]["value"] == "38%" and slide["slots"]["source"] == "Later (2026)"
    assert validate_content(spec, slide["slots"], slide["params"], []) == []
