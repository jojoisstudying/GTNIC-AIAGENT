"""Riset video per topik: cache 24 jam + pemilihan "live" vs "hemat kuota".

Checkbox "Live Tavily Search" di UI:
- dicentang   : cari fakta baru lewat Tavily (2 query), lalu simpan ke cache
- tidak       : pakai riset tersimpan untuk TOPIK YANG SAMA (maks 24 jam); bila belum ada, naskah dibuat
                tanpa riset (tanpa angka/statistik) dan pipeline mencatat event `video_research_skipped`.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from src import config

TTL_SEC = 24 * 3600


def _dir() -> Path:
    return config.OUTPUT_DIR / "video_research"


def _path(topic: str) -> Path:
    key = hashlib.md5(" ".join(topic.lower().split()).encode("utf-8")).hexdigest()
    return _dir() / f"{key}.json"


def save(topic: str, result: Dict[str, Any]) -> None:
    p = _path(topic)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"topic": topic, "saved_at": time.time(), "result": result},
                            ensure_ascii=False), encoding="utf-8")


def load(topic: str, *, now: Optional[float] = None, ttl: int = TTL_SEC) -> Optional[Dict[str, Any]]:
    p = _path(topic)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if (now if now is not None else time.time()) - float(data.get("saved_at", 0)) > ttl:
        return None
    result = data.get("result")
    return result if isinstance(result, dict) and result.get("ok") and result.get("context") else None


def make_researcher(ctx: Any, fresh: bool,
                    gather: Optional[Callable[..., Dict[str, Any]]] = None) -> Callable[[str], Dict[str, Any]]:
    """Kembalikan `researcher(topic)` untuk VideoPipeline sesuai pilihan `fresh`."""
    def researcher(topic: str) -> Dict[str, Any]:
        if not fresh:
            cached = load(topic)
            if cached:
                return cached
            return {"ok": False, "sources": [], "context": "",
                    "error": "Riset live dimatikan dan belum ada riset tersimpan (24 jam) untuk topik ini"}
        fn = gather
        if fn is None:
            from src.reels.agents.topic_research import gather_topic_research
            fn = gather_topic_research
        result = fn(topic, ctx=ctx)
        if result.get("ok"):
            try:
                save(topic, result)
            except OSError:
                pass  # cache gagal ditulis tidak boleh menggagalkan video
        return result
    return researcher
