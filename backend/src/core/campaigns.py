"""Logika kampanye: perencanaan item, breakdown analytics, dan evaluasi berbasis tujuan."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import select

from src.core.db import Campaign, ContentStrategyItem, EnterpriseProfile, PostAnalytics

ANGLES = ["Masalah yang dihadapi audiens", "Solusi dan cara kerjanya", "Bukti dan studi kasus",
          "Mitos vs fakta", "Ajakan bertindak"]
DEFAULT_SLOTS = ["09:00 WIB", "13:00 WIB", "18:30 WIB"]
MIN_SAMPLE = 3


def _d(v: str) -> datetime:
    return datetime.strptime(v, "%Y-%m-%d")


def best_real_format(session) -> str | None:
    rows = [r for r in session.scalars(select(PostAnalytics)).all()
            if not r.is_simulated and r.reach and r.ingestion_status == "complete"]
    by: dict[str, list[int]] = {}
    for r in rows:
        by.setdefault(r.format, []).append(r.reach)
    by = {k: v for k, v in by.items() if len(v) >= 2}
    return max(by, key=lambda k: sum(by[k]) / len(by[k])) if len(by) >= 2 else None


def plan_items(session, campaign: Campaign, posts: int = 5) -> list[ContentStrategyItem]:
    posts = max(1, min(posts, 14))
    start, end = _d(campaign.start_date), _d(campaign.end_date)
    if end < start:
        raise ValueError("end_date sebelum start_date")
    span = (end - start).days
    prof = session.scalars(select(EnterpriseProfile).order_by(EnterpriseProfile.id.desc())).first()
    pillars = json.loads(prof.content_pillars_json or "[]") if prof else []
    slots = (json.loads(prof.operating_preferences_json or "{}").get("preferred_slots") if prof else None) or DEFAULT_SLOTS
    pillars = pillars or ["Edukasi Bisnis"]
    best = best_real_format(session)
    other = "video" if best != "video" else "carousel"
    items = []
    for i in range(posts):
        day = start + timedelta(days=round(span * i / max(1, posts - 1)) if posts > 1 else 0)
        fmt = (best if i % 5 in (0, 1, 3) else other) if best else ("carousel" if i % 2 == 0 else "video")
        src = f"analytics_real(best_format={best})" if best else "campaign_plan_default"
        it = ContentStrategyItem(
            plan_date=day.strftime("%Y-%m-%d"), topic=f"{campaign.name}: {ANGLES[i % len(ANGLES)]}",
            format=fmt, content_pillar=pillars[i % len(pillars)], objective=campaign.objective[:128],
            target_segment=(campaign.target_audience or "Umum")[:128], scheduled_slot=slots[i % len(slots)],
            rationale=f"Bagian dari kampanye '{campaign.name}'. Pesan utama: {campaign.message[:200]} [strategy_source={src}]",
            status="draft", campaign_id=campaign.id)
        session.add(it)
        items.append(it)
    session.flush()
    return items


def _eng(r) -> float | None:
    parts = [r.likes, r.comments, r.shares, r.saves]
    if not r.reach or all(p is None for p in parts):
        return None
    return sum(p or 0 for p in parts) / r.reach


def _group(rows: Iterable, key) -> dict:
    out: dict = {}
    for r in rows:
        out.setdefault(key(r) or "tidak diketahui", []).append(r)
    res = {}
    for k, rs in out.items():
        reach = [r.reach for r in rs if r.reach is not None]
        eng = [e for e in map(_eng, rs) if e is not None]
        res[k] = {"posts": len(rs), "total_reach": sum(reach), "avg_reach": round(sum(reach) / len(reach), 1) if reach else None,
                  "avg_engagement_rate": round(sum(eng) / len(eng), 4) if eng else None,
                  "posts_without_reach_data": len(rs) - len(reach)}
    return res


def breakdown(rows: list) -> dict:
    ranked = sorted((r for r in rows if r.reach is not None), key=lambda r: r.reach, reverse=True)
    brief = lambda r: {"id": r.id, "topic": r.topic, "reach": r.reach, "engagement_rate": (round(_eng(r), 4) if _eng(r) is not None else None),
                       "is_simulated": r.is_simulated}
    return {"total_posts": len(rows), "simulated_posts": sum(bool(r.is_simulated) for r in rows),
            "by_pillar": _group(rows, lambda r: r.content_pillar), "by_format": _group(rows, lambda r: r.format),
            "by_date": _group(rows, lambda r: r.data_timestamp.strftime("%Y-%m-%d") if r.data_timestamp else None),
            "best": [brief(r) for r in ranked[:3]], "underperforming": [brief(r) for r in ranked[-3:]] if len(ranked) > 3 else []}


def primary_metric(objective: str) -> str:
    o = (objective or "").lower()
    if any(k in o for k in ("lead", "konversi", "penjualan", "konsultasi")):
        return "profile_visits"
    if any(k in o for k in ("engage", "edukasi", "interaksi", "komunitas")):
        return "engagement_rate"
    return "reach"


def evaluate(campaign: Campaign, rows: list) -> dict:
    metric = primary_metric(campaign.objective)
    targets = json.loads(campaign.performance_targets_json or "{}")
    if metric == "engagement_rate":
        vals = [e for e in map(_eng, rows) if e is not None]
        value = round(sum(vals) / len(vals), 4) if vals else None
    else:
        vals = [getattr(r, metric) for r in rows if getattr(r, metric) is not None]
        value = sum(vals) if vals else None
    target = targets.get(metric)
    if len(vals) < MIN_SAMPLE:
        status = "insufficient_data"
    elif target is None:
        status = "no_target"
    else:
        status = "achieved" if value >= target else "below_target"
    return {"primary_metric": metric, "value": value, "target": target, "status": status,
            "sample_size": len(vals), "min_sample": MIN_SAMPLE,
            "note": "Metrik utama dipilih dari tujuan kampanye; likes saja tidak dianggap keberhasilan bisnis. "
                    "Metrik yang tidak tersedia tidak dihitung sebagai nol."}


def campaign_rows(session, campaign_id: int) -> list:
    ids = [i for i in session.scalars(select(ContentStrategyItem.id).where(ContentStrategyItem.campaign_id == campaign_id)).all()]
    if not ids:
        return []
    return session.scalars(select(PostAnalytics).where(PostAnalytics.strategy_item_id.in_(ids))).all()
