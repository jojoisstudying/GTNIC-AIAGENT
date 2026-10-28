"""Riset berbasis TOPIK untuk video (fakta tentang topiknya, bukan tren media sosial).

`research_agent` lama mencari tren format/jam posting dari later.com dkk, sehingga tidak
menjawab pertanyaan seperti "Apa itu HTTPS". Modul ini mencari fakta tentang topik itu
sendiri lewat Tavily dan mengembalikan teks ringkas berisi sumber, supaya scriptwriter
hanya menulis klaim yang ada di sumber.
"""
from __future__ import annotations

from typing import Any, Optional

from src.core.http import redact_text
from src.core.pricing import provider_units
from src.carousel.tools.search import _get_tavily_key

TAVILY_URL = "https://api.tavily.com/search"


def _search(query: str, n: int, ctx: Any) -> list[dict]:
    token = _get_tavily_key(ctx)
    payload = {"query": query, "max_results": n, "search_depth": "basic", "api_key": token}
    if ctx is not None and getattr(ctx, "http", None):
        res = ctx.http.request("POST", TAVILY_URL, step="video_research", provider="tavily",
                               json=payload, units=provider_units("tavily")).json()
    else:
        from tavily import TavilyClient  # lazy import
        res = TavilyClient(api_key=token).search(query=query, max_results=n)
    return list(res.get("results", []) or [])


def gather_topic_research(topic: str, ctx: Any = None, *, max_sources: int = 5,
                          per_source_chars: int = 600, max_chars: int = 2800) -> dict:
    """Return {"ok", "sources": [{title,url,content}], "context": str, "error": Optional[str]}.

    Tidak pernah raise: kegagalan dikembalikan sebagai ok=False supaya pipeline bisa memilih
    melanjutkan tanpa riset (dan mencatat event peringatan).
    """
    queries = [topic, f"{topic} explained"]
    errors: list[str] = []
    merged: list[dict] = []
    seen: set[str] = set()

    for q in queries:
        try:
            results = _search(q, max_sources, ctx)
        except Exception as e:  # noqa: BLE001 - satu query gagal tidak boleh menggagalkan semuanya
            errors.append(f"{type(e).__name__}: {redact_text(str(e))}")
            continue
        for r in results:
            url = (r.get("url") or "").strip()
            content = " ".join(str(r.get("content") or "").split())
            if not url or not content or url in seen:
                continue
            seen.add(url)
            merged.append({"title": (r.get("title") or url).strip(), "url": url,
                           "content": content[:per_source_chars]})

    sources = merged[:max_sources]
    if not sources:
        return {"ok": False, "sources": [], "context": "",
                "error": "; ".join(errors) or "Tidak ada hasil pencarian untuk topik ini"}

    parts: list[str] = []
    used = 0
    for i, s in enumerate(sources, 1):
        block = f"[{i}] {s['title']} — {s['url']}\n{s['content']}"
        if used + len(block) > max_chars and parts:
            break
        parts.append(block)
        used += len(block)
    return {"ok": True, "sources": sources, "context": "\n\n".join(parts), "error": None}