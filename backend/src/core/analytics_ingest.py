"""Ingestion metrik Instagram asli ke PostAnalytics + riwayat snapshot + insight konservatif.

Prinsip yang dipegang:
- Hanya data nyata dari Graph API. Tidak ada angka contoh.
- Metrik yang tidak didukung untuk tipe media tertentu tetap ``NULL`` (bukan 0), dan
  daftar metrik yang benar-benar tersedia disimpan di ``metrics_available_json``.
- Setiap pengambilan disimpan sebagai snapshot agar tren performa bisa dilihat.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import select

from src.core.db import (AnalyticsInsight, ContentStrategyItem, PostAnalytics, PostAnalyticsSnapshot,
                         Publication, ingest_publication_metrics)

log = logging.getLogger("gtnic.analytics")
MIN_SAMPLE = 5

# Pemetaan nama metrik API -> kolom internal.
INSIGHT_FIELD_MAP = {
    "reach": "reach",
    "saved": "saves",
    "shares": "shares",
    "views": "views",
    "total_interactions": "total_interactions",
    "profile_visits": "profile_visits",
    "follows": "follower_delta",
}


def fetch_instagram_metrics(media_id: str) -> dict:
    """Ambil metrik satu media. Field yang tidak tersedia dibiarkan None."""
    from src.tools import instagram
    basic = instagram.get_media_metrics(media_id)
    ins = instagram.get_media_insights(media_id)
    out: dict = {
        "likes": basic.get("like_count"),
        "comments": basic.get("comments_count"),
        "permalink": basic.get("permalink"),
        "media_type": basic.get("media_type"),
        "posted_at": basic.get("timestamp"),
        "impressions": None,  # tidak didukung Media Insights saat ini (dipertahankan eksplisit)
        "link_clicks": None,  # tidak disediakan API media insight
    }
    for api_name, field in INSIGHT_FIELD_MAP.items():
        out[field] = ins.get(api_name)
    out["metrics_available"] = sorted(k for k, v in ins.items() if v is not None)
    return out


def _engagement_rate(metrics: dict) -> float | None:
    reach = metrics.get("reach")
    if not reach:
        return None
    parts = [metrics.get(k) for k in ("likes", "comments", "saves", "shares")]
    if all(p is None for p in parts):
        return None
    return round(sum(p or 0 for p in parts) / reach * 100, 2)


def store_snapshot(session, pub: Publication, metrics: dict, *, collected_at=None) -> PostAnalyticsSnapshot:
    """Simpan satu titik waktu metrik (riwayat tren)."""
    snap = PostAnalyticsSnapshot(
        publication_id=pub.id,
        media_id=pub.media_id,
        source="instagram_graph_api",
        reach=metrics.get("reach"),
        impressions=metrics.get("impressions"),
        views=metrics.get("views"),
        likes=metrics.get("likes"),
        comments=metrics.get("comments"),
        shares=metrics.get("shares"),
        saves=metrics.get("saves"),
        profile_visits=metrics.get("profile_visits"),
        follower_delta=metrics.get("follower_delta"),
        total_interactions=metrics.get("total_interactions"),
        engagement_rate=metrics.get("engagement_rate"),
        metrics_available_json=json.dumps(metrics.get("metrics_available") or [], ensure_ascii=False),
        collected_at=collected_at or datetime.now(timezone.utc),
    )
    session.add(snap)
    return snap


def ingest_publication(session, pub: Publication, fetch: Callable[[str], dict] | None = None) -> dict:
    """Tarik + simpan metrik untuk satu publikasi. Mengembalikan metrik mentah yang tersimpan."""
    fetch = fetch or fetch_instagram_metrics
    if not pub.media_id:
        raise ValueError("Publikasi belum punya media_id Instagram")
    metrics = dict(fetch(pub.media_id))
    if metrics.get("permalink") and not pub.permalink:
        pub.permalink = metrics["permalink"]
    metrics["engagement_rate"] = _engagement_rate(metrics)
    item = None
    if pub.strategy_item_id:
        item = session.get(ContentStrategyItem, pub.strategy_item_id)
    metrics.update(format=_fmt_of(pub, metrics), content_pillar=getattr(item, "content_pillar", None),
                   topic=getattr(item, "topic", None), is_simulated=False)
    row = ingest_publication_metrics(session, pub, metrics, source="instagram_graph_api")
    if item and not row.strategy_item_id:
        row.strategy_item_id = item.id
    store_snapshot(session, pub, metrics)
    session.commit()
    return metrics


def _fmt_of(pub: Publication, metrics: dict) -> str:
    if pub.media_type:
        return pub.media_type
    media_type = (metrics.get("media_type") or "").upper()
    return {"VIDEO": "reel", "CAROUSEL_ALBUM": "carousel", "IMAGE": "image"}.get(media_type, "unknown")


def ingest_all(session_factory, fetch: Callable[[str], dict] = fetch_instagram_metrics,
               window_days: int = 30) -> dict:
    """Perbarui metrik semua publikasi 'published' dalam ``window_days``.

    Kegagalan satu post tidak menghentikan lainnya.
    """
    since = datetime.now(timezone.utc) - timedelta(days=window_days)
    done = failed = 0
    errors: list[dict] = []
    with session_factory() as session:
        pubs = session.scalars(select(Publication).where(
            Publication.status == "published", Publication.media_id.is_not(None))).all()
        for pub in pubs:
            published_at = pub.published_at
            if published_at is not None:
                if published_at.tzinfo is None:
                    published_at = published_at.replace(tzinfo=timezone.utc)
                if published_at < since and pub.published_at is not None:
                    # post lama tetap diinginkan untuk tren, tapi tidak menahan window default
                    continue
            try:
                ingest_publication(session, pub, fetch)
                done += 1
            except Exception as exc:  # noqa: BLE001
                session.rollback()
                failed += 1
                errors.append({"publication_id": pub.id, "media_id": pub.media_id, "error": str(exc)[:300]})
                log.warning("Ingestion media %s gagal: %s", pub.media_id, exc)
        created = generate_real_insights(session)
        session.commit()
    return {"ingested": done, "failed": failed, "new_insights": created, "errors": errors}


def generate_real_insights(session) -> int:
    """Insight hanya dari data NYATA (non-simulated). Data < MIN_SAMPLE → tidak membuat kesimpulan."""
    rows = [r for r in session.scalars(select(PostAnalytics)).all()
            if not r.is_simulated and r.ingestion_status == "complete" and r.reach]
    if len(rows) < MIN_SAMPLE:
        log.info("Data nyata %d < %d; insight tidak dibuat.", len(rows), MIN_SAMPLE)
        return 0
    by_fmt: dict[str, list] = {}
    for r in rows:
        by_fmt.setdefault(r.format, []).append(r)
    by_fmt = {k: v for k, v in by_fmt.items() if len(v) >= 2}
    if len(by_fmt) < 2:
        return 0
    avg = {k: sum(r.reach for r in v) / len(v) for k, v in by_fmt.items()}
    best, worst = max(avg, key=avg.get), min(avg, key=avg.get)
    title = f"Format {best} menjangkau lebih luas dari {worst}"
    obs = (f"Rata-rata reach {best}: {avg[best]:.0f} (n={len(by_fmt[best])}) vs {worst}: {avg[worst]:.0f} "
           f"(n={len(by_fmt[worst])}). Korelasi, belum tentu kausal.")
    if session.scalars(select(AnalyticsInsight).where(
            AnalyticsInsight.title == title, AnalyticsInsight.observation == obs)).first():
        return 0
    session.add(AnalyticsInsight(
        title=title, observation=obs,
        recommended_action=f"Uji tambahan porsi {best} pada 1–2 slot minggu depan lalu bandingkan ulang.",
        confidence="medium" if len(rows) >= 10 else "preliminary",
        data_points_json=json.dumps({"sample_size": len(rows), "record_ids": [r.id for r in rows],
                                     "avg_reach": avg, "sources": ["instagram_graph_api"],
                                     "is_simulated": False}),
        applied_to_strategy=False))
    return 1
