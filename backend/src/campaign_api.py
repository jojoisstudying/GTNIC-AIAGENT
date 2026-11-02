"""Endpoint manajemen kampanye dan analytics per kampanye."""
import json
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from src.core import auth
from src.core.campaigns import breakdown, campaign_rows, evaluate, plan_items
from src.core.db import Campaign, ContentStrategyItem, PostAnalytics, SessionLocal

router = APIRouter(prefix="/api/v1")
STATUSES = {"draft", "active", "completed", "cancelled"}


def _date(v: str) -> str:
    try:
        datetime.strptime(v, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Tanggal harus YYYY-MM-DD: {v}")
    return v


class CampaignIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    objective: str = Field(min_length=2, max_length=128)
    target_audience: str = ""
    start_date: str
    end_date: str
    products: List[str] = []
    message: str = ""
    content_requirements: str = ""
    performance_targets: Dict[str, float] = {}


class CampaignPatch(BaseModel):
    name: Optional[str] = None
    objective: Optional[str] = None
    target_audience: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    products: Optional[List[str]] = None
    message: Optional[str] = None
    content_requirements: Optional[str] = None
    performance_targets: Optional[Dict[str, float]] = None
    status: Optional[str] = None


class AttachItems(BaseModel):
    item_ids: List[int]


def _ser(c: Campaign) -> dict:
    return {"id": c.id, "name": c.name, "objective": c.objective, "target_audience": c.target_audience,
            "start_date": c.start_date, "end_date": c.end_date, "products": json.loads(c.products_json or "[]"),
            "message": c.message, "content_requirements": c.content_requirements,
            "performance_targets": json.loads(c.performance_targets_json or "{}"), "status": c.status}


def _get(s, cid: int) -> Campaign:
    c = s.get(Campaign, cid)
    if not c:
        raise HTTPException(status_code=404, detail="Kampanye tidak ditemukan")
    return c


@router.post("/campaigns", dependencies=[Depends(auth.verify_api_key)])
def create_campaign(req: CampaignIn):
    if _date(req.end_date) < _date(req.start_date):
        raise HTTPException(status_code=422, detail="end_date tidak boleh sebelum start_date")
    with SessionLocal() as s:
        c = Campaign(name=req.name, objective=req.objective, target_audience=req.target_audience,
                     start_date=req.start_date, end_date=req.end_date, message=req.message,
                     products_json=json.dumps(req.products, ensure_ascii=False),
                     content_requirements=req.content_requirements,
                     performance_targets_json=json.dumps(req.performance_targets))
        s.add(c); s.commit()
        return _ser(c)


@router.get("/campaigns")
def list_campaigns(status: Optional[str] = None):
    with SessionLocal() as s:
        q = select(Campaign).order_by(desc(Campaign.id))
        if status:
            q = q.where(Campaign.status == status)
        return {"items": [_ser(c) for c in s.scalars(q).all()]}


@router.get("/campaigns/{cid}")
def get_campaign(cid: int):
    with SessionLocal() as s:
        c = _get(s, cid)
        items = s.scalars(select(ContentStrategyItem).where(ContentStrategyItem.campaign_id == cid)
                          .order_by(ContentStrategyItem.plan_date)).all()
        by = Counter(i.status for i in items)
        return {**_ser(c), "progress": {"total_items": len(items), "published": by.get("published", 0),
                                         "by_status": dict(by)},
                "items": [{"id": i.id, "plan_date": i.plan_date, "scheduled_slot": i.scheduled_slot, "topic": i.topic,
                           "format": i.format, "content_pillar": i.content_pillar, "status": i.status} for i in items]}


@router.patch("/campaigns/{cid}", dependencies=[Depends(auth.verify_api_key)])
def patch_campaign(cid: int, req: CampaignPatch):
    with SessionLocal() as s:
        c = _get(s, cid)
        d = req.model_dump(exclude_none=True)
        if "status" in d and d["status"] not in STATUSES:
            raise HTTPException(status_code=400, detail=f"Status tidak valid: {d['status']}")
        for k in ("start_date", "end_date"):
            if k in d:
                _date(d[k])
        for k in ("name", "objective", "target_audience", "start_date", "end_date", "message",
                  "content_requirements", "status"):
            if k in d:
                setattr(c, k, d[k])
        if "products" in d:
            c.products_json = json.dumps(d["products"], ensure_ascii=False)
        if "performance_targets" in d:
            c.performance_targets_json = json.dumps(d["performance_targets"])
        if c.end_date < c.start_date:
            raise HTTPException(status_code=422, detail="end_date tidak boleh sebelum start_date")
        c.updated_at = datetime.now(timezone.utc)
        s.commit()
        return _ser(c)


@router.post("/campaigns/{cid}/plan", dependencies=[Depends(auth.verify_api_key)])
def plan_campaign(cid: int, posts: int = 5):
    """Membuat item kalender (draft) yang tersebar sepanjang periode kampanye."""
    with SessionLocal() as s:
        c = _get(s, cid)
        if c.status in {"completed", "cancelled"}:
            raise HTTPException(status_code=409, detail=f"Kampanye berstatus {c.status}.")
        try:
            items = plan_items(s, c, posts)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        s.commit()
        return {"campaign_id": cid, "created": [{"id": i.id, "plan_date": i.plan_date, "topic": i.topic,
                                                  "format": i.format, "scheduled_slot": i.scheduled_slot} for i in items]}


@router.post("/campaigns/{cid}/items", dependencies=[Depends(auth.verify_api_key)])
def attach_items(cid: int, req: AttachItems):
    with SessionLocal() as s:
        _get(s, cid)
        n = 0
        for i in s.scalars(select(ContentStrategyItem).where(ContentStrategyItem.id.in_(req.item_ids))).all():
            i.campaign_id = cid; n += 1
        s.commit()
        return {"attached": n}


@router.get("/analytics/campaigns/{cid}")
def campaign_analytics(cid: int):
    with SessionLocal() as s:
        c = _get(s, cid)
        rows = campaign_rows(s, cid)
        return {"campaign": _ser(c), "evaluation": evaluate(c, rows), **breakdown(rows)}


@router.get("/analytics/breakdown")
def analytics_breakdown(campaign_id: Optional[int] = None, format: Optional[str] = None,
                        pillar: Optional[str] = None, include_simulated: bool = True):
    with SessionLocal() as s:
        rows = campaign_rows(s, campaign_id) if campaign_id else s.scalars(select(PostAnalytics)).all()
        rows = [r for r in rows if (not format or r.format == format) and (not pillar or r.content_pillar == pillar)
                and (include_simulated or not r.is_simulated)]
        return breakdown(rows)
