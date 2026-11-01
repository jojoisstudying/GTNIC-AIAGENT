"""Riset video per topik: checkbox 'Live Tavily Search' (live vs cache 24 jam)."""
import pytest

from src import config
from src.video import research_cache as rc

RESULT = {"ok": True, "context": "[1] Cloudflare - https://c.test\nHTTPS memakai TLS.",
          "sources": [{"url": "https://c.test"}], "error": None}


@pytest.fixture(autouse=True)
def out_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path / "output")
    return tmp_path / "output"


def test_save_then_load_roundtrip_and_topic_normalisation():
    rc.save("Apa itu HTTPS", RESULT)
    assert rc.load("apa   itu  https") == RESULT           # huruf besar/spasi ganda tidak membedakan topik
    assert rc.load("topik lain") is None


def test_cache_expires_after_ttl():
    rc.save("Apa itu HTTPS", RESULT)
    assert rc.load("Apa itu HTTPS", now=__import__("time").time() + rc.TTL_SEC + 60) is None


def test_fresh_runs_live_research_and_saves_it():
    calls = []

    def gather(topic, ctx=None):
        calls.append((topic, ctx))
        return RESULT

    res = rc.make_researcher("CTX", True, gather=gather)("Apa itu HTTPS")
    assert res == RESULT and calls == [("Apa itu HTTPS", "CTX")]
    assert rc.load("Apa itu HTTPS") == RESULT


def test_failed_live_research_is_not_cached():
    res = rc.make_researcher(None, True, gather=lambda t, ctx=None: {"ok": False, "error": "boom"})("t")
    assert res["ok"] is False
    assert rc.load("t") is None


def test_unchecked_uses_cache_and_never_calls_tavily():
    rc.save("Apa itu HTTPS", RESULT)

    def gather(*a, **k):
        raise AssertionError("tidak boleh memanggil Tavily saat checkbox mati")

    assert rc.make_researcher(None, False, gather=gather)("Apa itu HTTPS") == RESULT


def test_unchecked_without_cache_returns_readable_skip_reason():
    res = rc.make_researcher(None, False, gather=lambda *a, **k: 1 / 0)("topik baru")
    assert res["ok"] is False and res["context"] == "" and "Riset live dimatikan" in res["error"]
