"""Tool riset: pencarian web DIBATASI ke sumber tepercaya. later.com selalu dicari lebih dulu (sumber utama),
lalu ditambah sumber lain untuk cross-check."""
from src import config
from src.core.http import HttpClient, redact_text
from src.core.keys import KeyPool
from src.core.pricing import provider_units

LATER = ["later.com"]
OTHERS = ["buffer.com", "sproutsocial.com", "hootsuite.com"]


def _get_tavily_key(ctx=None) -> str:
    emitter = ctx.emitter if ctx else None
    pool = getattr(ctx, "tavily_pool", None)
    if pool is None:
        pool = KeyPool("tavily", emitter=emitter)
    return pool.get_current_key()


def _search(tv, query: str, domains: list[str], n: int, http: HttpClient | None = None,
            api_key: str | None = None) -> list[dict]:
    try:
        if http:
            res = http.request("POST", "https://api.tavily.com/search", step="research",
                               provider="tavily", json={"query": query, "max_results": n,
                                                        "include_domains": domains,
                                                        "api_key": api_key},
                               units=provider_units("tavily")).json()
        else:
            res = tv.search(query=query, max_results=n, include_domains=domains)
    except Exception:
        return []
    return [{"title": r.get("title"), "url": r.get("url"), "published": r.get("published_date"),
             "content": (r.get("content") or "")[:1000]} for r in res.get("results", [])]


def search_social_trends(query: str, *, ctx=None) -> dict:
    try:
        token = _get_tavily_key(ctx)
        tv = None
        if not (ctx and ctx.http):
            from tavily import TavilyClient  # lazy import
            tv = TavilyClient(api_key=token)
        http = ctx.http if ctx else None
        later = _search(tv, query, LATER, 2, http, api_key=token)
        others = _search(tv, query, OTHERS, 3, http, api_key=token)
        seen, merged = set(), []
        for r in later + others:
            if r["url"] and r["url"] not in seen:
                seen.add(r["url"])
                merged.append(r)
        note = "" if later else "later.com tidak punya hasil untuk query ini"
        return {"results": merged, "note": note}
    except Exception as e:  # agent harus tetap jalan kalau satu tool gagal
        return {"results": [], "error": f"{type(e).__name__}: {redact_text(str(e))}"}
