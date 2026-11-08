"""Regresi: konsistensi sumber riset -> research_used (tanpa LLM, tanpa jaringan).

Bug asal: URL di prompt dipotong pemangkas token (``.../instag…``), model menyalin
URL terpotong itu, lalu validator menolaknya seolah URL karangan.
"""
import json

import pytest

from src.carousel import sources as S
from src.carousel.agents import planner
from src.core import tokens as token_budget

RESEARCH = {
    "sources": [
        "https://later.com/blog/instagram-reels-trends",
        "https://later.com/blog/best-time-to-post-on-instagram",
        "https://sproutsocial.com/insights/instagram-trends/",
    ],
    "topic_candidates": [
        {"topic": "tren", "source_urls": ["https://later.com/blog/instagram-reels-trends"]},
    ],
    "posting_time": {"instagram": "5 AM", "source_urls": ["https://buffer.com/resources/x"]},
    "facts": {"stats": [], "quotes": []},
}


def _plan(research_used):
    return {"format": "single_image", "slides": [], "caption": "c", "hashtags": ["#a"],
            "schedule": {"slots": [{"time": "5 AM"}], "ab_test": "x"},
            "research_used": research_used}


def _ref_issues(research_used, research=RESEARCH):
    return [i for i in planner.validate(_plan(research_used), "", research, "topik",
                                        history=[], approved={})
            if "research_used" in i]


# ---------------------------------------------------------------- 1. URL valid diterima
def test_valid_url_in_research_is_accepted():
    assert _ref_issues(["https://later.com/blog/instagram-reels-trends"]) == []


def test_url_outside_top_level_sources_but_present_in_research_is_accepted():
    """URL dari posting_time.source_urls tetap asli (dulu sudah didukung, jangan regresi)."""
    assert _ref_issues(["https://buffer.com/resources/x"]) == []


# ---------------------------------------------------------------- 2. URL karangan ditolak
def test_unknown_url_is_rejected():
    issues = _ref_issues(["https://evil.example/made-up-article"])
    assert issues and "evil.example" in issues[0]


def test_lookalike_domain_is_rejected():
    """Domain mirip bukan bukti; harus tetap ditolak."""
    assert _ref_issues(["https://later.com.evil.example/blog/instagram-reels-trends"])


def test_different_article_on_same_domain_is_rejected():
    assert _ref_issues(["https://later.com/blog/artikel-lain-yang-tidak-ada"])


# ---------------------------------------------------------------- 3. Markdown
def test_markdown_link_is_extracted_and_accepted():
    md = "[Later Trends](https://later.com/blog/instagram-reels-trends)"
    plan = _plan([md])
    planner._resolve_research_used(plan, RESEARCH)
    assert plan["research_used"] == ["https://later.com/blog/instagram-reels-trends"]
    assert _ref_issues(plan["research_used"]) == []


def test_markdown_link_without_scheme_text_is_ignored_by_extractor():
    """Label Markdown bukan URL; hanya target yang diambil."""
    assert S.clean_url_text("[lihat di sini](https://a.example/x)") == "https://a.example/x"


# ---------------------------------------------------------------- 4. Trailing slash
def test_trailing_slash_is_normalized_for_comparison():
    plan = _plan(["https://sproutsocial.com/insights/instagram-trends/"])
    planner._resolve_research_used(plan, RESEARCH)
    assert plan["research_used"] == ["https://sproutsocial.com/insights/instagram-trends/"]


def test_trailing_slash_does_not_merge_different_articles():
    assert S.normalize_url("https://a.example/x/") == S.normalize_url("https://a.example/x")
    assert S.normalize_url("https://a.example/x") != S.normalize_url("https://a.example/y")
    assert S.normalize_url("https://a.example/x/1") != S.normalize_url("https://a.example/x/2")


def test_encoded_path_is_not_decoded_into_a_different_article():
    """%2F tidak boleh jadi '/', kalau tidak dua artikel berbeda dianggap sama."""
    assert S.normalize_url("https://a.example/x%2Fy") != S.normalize_url("https://a.example/x/y")
    assert S.normalize_url("https://a.example/%41") == S.normalize_url("https://a.example/A")


def test_www_scheme_and_tracking_params_are_equivalent():
    a = S.normalize_url("http://www.a.example/x?utm_source=x&id=7&fbclid=z")
    b = S.normalize_url("https://a.example/x/?id=7")
    assert a == b
    # urutan query tidak mengubah artikel
    assert S.normalize_url("https://a.example/x?a=1&b=2") == S.normalize_url("https://a.example/x?b=2&a=1")


# ---------------------------------------------------------------- 5. Duplikat
def test_duplicate_sources_are_collapsed():
    research = {"sources": ["https://a.example/x", "https://a.example/x/",
                            "https://www.a.example/x?utm_source=n", "https://b.example/y"]}
    catalog = S.SourceCatalog.from_research(research)
    assert len(catalog) == 2
    assert catalog.urls[0] == "https://a.example/x"


def test_duplicate_research_used_entries_are_not_repeated():
    plan = _plan(["https://later.com/blog/instagram-reels-trends",
                  "S1", "https://later.com/blog/instagram-reels-trends/"])
    planner._resolve_research_used(plan, RESEARCH)
    assert plan["research_used"] == ["https://later.com/blog/instagram-reels-trends"]


# ---------------------------------------------------------------- 6. URL tidak pernah dipotong
def test_truncate_values_never_breaks_a_url():
    url = "https://later.com/blog/best-time-to-post-on-instagram"
    assert token_budget.truncate_values(url, 30) == url
    for node in ([url], {"sources": [url]}, {"posting_time": {"source_urls": [url]}}):
        assert url in json.dumps(token_budget.truncate_values(node, 30), ensure_ascii=False)


def test_truncate_values_keeps_url_whole_inside_prose():
    url = "https://later.com/blog/best-time-to-post-on-instagram"
    text = "Menurut artikel yang sangat panjang ini " + url + " waktu terbaik adalah pagi."
    out = token_budget.truncate_values(text, 40)
    assert url in out


def test_clip_text_never_breaks_a_url():
    url = "https://later.com/blog/best-time-to-post-on-instagram"
    assert token_budget.clip_text(url, 12) == url


def test_compact_research_keeps_urls_whole():
    long_url = "https://example.com/" + "a" * 200
    compact = planner._compact_research({
        "sources": [long_url],
        "trending_formats": [{"name": "n" * 200, "source_url": long_url}],
        "topic_candidates": [{"topic": "t" * 200, "source_urls": [long_url]}],
        "posting_time": {"source_urls": [long_url], "instagram": "5 AM"},
        "facts": {"stats": [], "quotes": []},
    })
    dumped = json.dumps(compact, ensure_ascii=False)
    assert long_url in dumped
    assert "…" not in long_url


def test_truncated_url_from_old_run_is_corrected_when_unambiguous():
    """URL terpotong model lama tetap bisa dikoreksi bila hanya satu kandidat."""
    catalog = S.SourceCatalog.from_research(RESEARCH)
    assert catalog.resolve("https://later.com/blog/instagram-re…") == \
        "https://later.com/blog/instagram-reels-trends"


def test_ambiguous_truncated_url_is_not_guessed():
    """Dua artikel berawalan sama: jangan menebak, tolak supaya tidak salah sumber."""
    research = {"sources": ["https://a.example/best-time-instagram",
                            "https://a.example/best-time-tiktok"]}
    catalog = S.SourceCatalog.from_research(research)
    assert catalog.resolve("https://a.example/best-t…") is None


# ---------------------------------------------------------------- 7. Sumber kosong
def test_empty_research_rejects_any_reference():
    for research in ({}, {"sources": []}, {"sources": [], "facts": {}}, None):
        issues = _ref_issues(["https://later.com/blog/instagram-reels-trends"], research or {})
        assert issues, research


def test_empty_research_renders_explicit_no_source_instruction():
    block = S.SourceCatalog.from_research({}).prompt_block()
    assert "TIDAK ADA SUMBER" in block and "[]" in block


def test_none_research_used_is_fine():
    assert _ref_issues([]) == [] and _ref_issues(None) == []


# ---------------------------------------------------------------- 8. Banyak sumber
def test_multiple_sources_resolve_independently():
    refs = ["https://later.com/blog/instagram-reels-trends",
            "https://later.com/blog/best-time-to-post-on-instagram",
            "https://sproutsocial.com/insights/instagram-trends"]
    plan = _plan(refs)
    planner._resolve_research_used(plan, RESEARCH)
    # Ketiga referensi valid; nilai disalin dari katalog riset (S3 memang bertrailing slash).
    assert len(plan["research_used"]) == 3
    assert [u.rstrip("/") for u in plan["research_used"]] == refs
    assert _ref_issues(refs) == []


def test_mixed_valid_and_invalid_only_reports_the_invalid_one():
    issues = _ref_issues(["https://later.com/blog/instagram-reels-trends",
                          "https://evil.example/fake"])
    assert len(issues) == 1 and "evil.example" in issues[0]
    assert "instagram-reels-trends" not in issues[0]


def test_source_ids_are_stable_and_map_to_real_urls():
    catalog = S.SourceCatalog.from_research(RESEARCH)
    assert catalog.get("S1").url == "https://later.com/blog/instagram-reels-trends"
    assert catalog.get("s2").url == "https://later.com/blog/best-time-to-post-on-instagram"
    assert catalog.get("S99") is None


def test_prompt_lists_only_verified_sources():
    block = S.SourceCatalog.from_research(RESEARCH).prompt_block()
    for url in RESEARCH["sources"]:
        assert url.rstrip("/") in block
    assert "evil.example" not in block


# ---------------------------------------------------------------- pesan error
def test_reference_failure_has_readable_indonesian_message():
    msg = planner.summarize_issues(_ref_issues(["https://evil.example/fake"]))
    assert "tidak tersedia dalam hasil riset" in msg
    assert "research_used" not in msg and "{" not in msg
    assert "riset ulang" in msg.lower()


def test_other_validation_failure_message_is_also_readable():
    msg = planner.summarize_issues(["caption kosong atau lebih dari 2200 karakter"])
    assert msg.startswith("Konten belum berhasil disusun")
    assert "research_used" not in msg
    assert "caption kosong" not in msg


def test_validate_still_rejects_other_rule_violations():
    """Validasi sumber tidak boleh melonggarkan aturan lain."""
    plan = _plan([])
    issues = planner.validate(plan, "", RESEARCH, "topik", history=[], approved={})
    assert any("caption" in i for i in issues) or any("slide" in i for i in issues)


# ---------------------------------------------------------------- verifikasi sumber riset
def test_research_sources_without_search_trace_are_dropped():
    from src.carousel.agents import research_agent as R
    gathered = [{"tool": "search_social_trends",
                 "result": {"results": [{"url": "https://later.com/blog/instagram-reels-trends"}]}}]
    data = {"sources": ["https://later.com/blog/instagram-reels-trends",
                        "https://karangan.example/tidak-ada"]}
    out, warnings = R.verify_sources(data, gathered)
    assert out["sources"] == ["https://later.com/blog/instagram-reels-trends"]
    assert warnings and "karangan.example" in warnings[0]


def test_research_sources_kept_when_all_verified():
    from src.carousel.agents import research_agent as R
    gathered = [{"tool": "search_social_trends",
                 "result": {"results": [{"url": "https://later.com/blog/instagram-reels-trends/"}]}}]
    data = {"sources": ["https://later.com/blog/instagram-reels-trends"]}
    out, warnings = R.verify_sources(data, gathered)
    assert out["sources"] == ["https://later.com/blog/instagram-reels-trends"]
    assert warnings == []


def test_research_sources_kept_with_warning_when_nothing_matches():
    """Jangan hapus seluruh riset; beri peringatan supaya operator memverifikasi."""
    from src.carousel.agents import research_agent as R
    data = {"sources": ["https://karangan.example/a"]}
    out, warnings = R.verify_sources(data, [])
    assert out["sources"] == ["https://karangan.example/a"]
    assert warnings and "verifikasi manual" in warnings[0]


def test_research_sources_empty_is_noop():
    from src.carousel.agents import research_agent as R
    assert R.verify_sources({"sources": []}, [])[1] == []
    assert R.verify_sources({}, [])[1] == []
