"""Ingestion metrik Instagram asli ke PostAnalytics + insight konservatif dari data nyata."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import select

from src.core.db import (AnalyticsInsight, ContentStrategyItem, Publication, ingest_publication_metrics)

log = logging.getLogger("gtnic.analytics")
MIN_SAMPLE = 5


def fetch_instagram_metrics(media_id: str) -> dict:
    from src.tools import instagram
    basic = instagram.get_media_metrics(media_id)
    ins = instagram.get_media_insights(media_id)
    return {
        "likes": basic.get("like_count"), "comments": basic.get("comments_count"),
        "reach": ins.get("reach"), "saves": ins.get("saved"), "shares": ins.get("shares"),
        "impressions": ins.get("views"), "profile_visits": ins.get("profile_visits"),
        "follower_delta": ins.get("follows"), "link_clicks": None,  # link_clicks tidak disediakan API media insight
        "permalink": basic.get("permalink"),
    }


def ingest_all(session_factory, fetch: Callable[[str], dict] = fetch_instagram_metrics,
               window_days: int = 30) -> dict:
    """Perbarui metrik semua publikasi 'published' dalam ``window_days``. Kegagalan satu post tidak menghentikan lainnya."""
    since = datetime.now(timezone.utc) - timedelta(days=window_days)
    done = failed = 0
    with session_factory() as session:
        pubs = session.scalars(select(Publication).where(
            Publication.status == "published", Publication.media_id.is_not(None))).all()
        for pub in pubs:
            if pub.published_at and pub.published_at.replace(tzinfo=pub.published_at.tzinfo or timezone.utc) < since:
                continue
            item = session.scalars(select(ContentStrategyItem).where(
                ContentStrategyItem.run_id == pub.run_id)).first()
            try:
                metrics = dict(fetch(pub.media_id))
            except Exception as exc:
                failed += 1
                log.warning("Ingestion media %s gagal: %s", pub.media_id, exc)
                continue
            if metrics.get("permalink") and not pub.permalink:
                pub.permalink = metrics["permalink"]
            metrics.update(format=getattr(item, "format", None), content_pillar=getattr(item, "content_pillar", None),
                           topic=getattr(item, "topic", None), is_simulated=False)
            row = ingest_publication_metrics(session, pub, metrics, source="instagram_graph_api")
            if item:
                row.strategy_item_id = item.id
            done += 1
        session.commit()
        created = generate_real_insights(session)
        session.commit()
    return {"ingested": done, "failed": failed, "new_insights": created}


def generate_real_insights(session) -> int:
    """Insight hanya dari data NYATA (non-simulated). Data < MIN_SAMPLE → tidak membuat kesimpulan."""
    from src.core.db import PostAnalytics
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
        confidence="medium" if len(rows) >= 10 else "pre",
        data_points_json=json.dumps({"sample_size": len(rows), "record_ids": [r.id for r in rows],
                                     "avg_reach": avg, "sources": ["instagram_graph_api"],
                                     "is_simulated": False}),
        applied_to_strategy=False))
    return 1
