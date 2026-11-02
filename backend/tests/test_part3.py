import json

from src.carousel.agents.research_agent import normalize_candidates
from src.carousel.tools import asset_library as al


def test_candidates_validated_against_tool_results():
    gathered = [{"results": [{"url": "https://later.com/blog/x", "content": "dirilis 12 Maret 2026"}]}]
    data = {"topic_candidates": [
        {"topic": "A", "relevance_score": 85, "source_urls": ["https://later.com/blog/x", "https://karangan.id"],
         "source_date": "12 Maret 2026", "relevance_reason": "cocok", "recommended_format": "video"},
        {"topic": "B", "relevance_score": 0.9, "source_urls": ["https://karangan.id"], "source_date": "1 Januari 2020"},
        {"topic": "", "relevance_score": 1}]}
    out, warns = normalize_candidates(data, gathered)
    a, b = out["topic_candidates"]
    assert a["topic"] == "A" and a["relevance_score"] == 0.85 and a["source_urls"] == ["https://later.com/blog/x"]
    assert a["source_date"] == "12 Maret 2026" and a["recommended_format"] == "video"
    assert b["relevance_score"] == 0.5 and b["source_date"] is None and "terverifikasi" in b["risk_notes"]
    assert not warns and normalize_candidates({}, [])[1]


def test_asset_permissions(tmp_path, monkeypatch):
    monkeypatch.setattr(al, "DB", tmp_path / "a.db")
    f = tmp_path / "x.png"; f.write_bytes(b"x")
    legacy = al.add_asset(str(f), ["logo"])                       # tanpa metadata izin
    assert al.is_allowed(al.get_asset(legacy), "social_post") and not al.is_allowed(al.get_asset(legacy), "ads")
    al.set_permissions(legacy, source_type="brand_owned", allowed_uses=["internal"])
    assert not al.is_allowed(al.get_asset(legacy), "social_post")
    al.set_permissions(legacy, allowed_uses=["social_post", "ads"])
    assert al.is_allowed(al.get_asset(legacy), "ads")
    try:
        al.set_permissions(legacy, allowed_uses=["bebas"]); assert False
    except ValueError:
        pass
    pending = al.add_asset(str(tmp_path / "y.png"), ["logo"], status="pending_review", allowed_uses=["social_post"])
    assert not al.is_allowed(al.get_asset(pending), "social_post")
