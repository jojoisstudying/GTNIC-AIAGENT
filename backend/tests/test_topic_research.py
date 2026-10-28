"""gather_topic_research: riset fakta tentang topik (bukan tren media sosial)."""
from types import SimpleNamespace

from src.reels.agents import topic_research as tr


class FakeResp:
    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


class FakeHttp:
    def __init__(self, by_query):
        self.by_query = by_query
        self.calls = []

    def request(self, method, url, *, step, provider, json=None, units=None, **kw):
        self.calls.append(json)
        out = self.by_query[json["query"]]
        if isinstance(out, Exception):
            raise out
        return FakeResp({"results": out})


def _ctx(http):
    return SimpleNamespace(http=http)


def test_merges_dedups_truncates_and_builds_context(monkeypatch):
    monkeypatch.setattr(tr, "_get_tavily_key", lambda ctx=None: "k")
    shared = {"title": "Cloudflare", "url": "https://c.test/a", "content": "HTTPS " * 300}
    http = FakeHttp({
        "Apa itu HTTPS": [shared, {"title": "MDN", "url": "https://m.test/b", "content": "TLS mengenkripsi lalu lintas."}],
        "Apa itu HTTPS explained": [shared, {"title": "kosong", "url": "https://e.test/c", "content": ""}],
    })
    res = tr.gather_topic_research("Apa itu HTTPS", _ctx(http), per_source_chars=100)

    assert res["ok"] is True
    assert [s["url"] for s in res["sources"]] == ["https://c.test/a", "https://m.test/b"]  # dedup, tanpa konten kosong
    assert all(len(s["content"]) <= 100 for s in res["sources"])
    assert res["context"].startswith("[1] Cloudflare — https://c.test/a")
    assert "include_domains" not in http.calls[0]  # bukan pencarian terbatas situs media sosial


def test_one_query_failing_still_returns_other_results(monkeypatch):
    monkeypatch.setattr(tr, "_get_tavily_key", lambda ctx=None: "k")
    http = FakeHttp({
        "t": RuntimeError("timeout"),
        "t explained": [{"title": "A", "url": "https://a.test", "content": "isi"}],
    })
    res = tr.gather_topic_research("t", _ctx(http))
    assert res["ok"] is True and len(res["sources"]) == 1


def test_total_failure_returns_ok_false_without_raising(monkeypatch):
    monkeypatch.setattr(tr, "_get_tavily_key", lambda ctx=None: "k")
    http = FakeHttp({"t": RuntimeError("boom"), "t explained": RuntimeError("boom")})
    res = tr.gather_topic_research("t", _ctx(http))
    assert res["ok"] is False and res["sources"] == [] and "boom" in res["error"]


def test_missing_api_key_returns_ok_false(monkeypatch):
    def no_key(ctx=None):
        raise RuntimeError("TAVILY key tidak ada")
    monkeypatch.setattr(tr, "_get_tavily_key", no_key)
    res = tr.gather_topic_research("t", _ctx(FakeHttp({})))
    assert res["ok"] is False