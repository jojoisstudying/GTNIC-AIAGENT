"""Tests for Enterprise Profile, Strategy Calendar, Analytics & Feedback Loop (FEATURE-01, FEATURE-02, FEATURE-03)."""
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api import app, SessionLocal
from src.core.db import Base, EnterpriseProfile, ContentStrategyItem, PostAnalytics, AnalyticsInsight
from src.core.strategy import SAMPLE_ENTERPRISE_PROFILE


@pytest.fixture()
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr("src.api.SessionLocal", factory)
    monkeypatch.setattr("src.core.strategy.SessionLocal", factory)
    return TestClient(app)


def test_enterprise_profile_get_and_update(client):
    res = client.get("/api/v1/enterprise/profile")
    assert res.status_code == 200
    data = res.json()
    assert data["company_name"] == "Resilience Digital Solusindo"
    assert data["completeness_score"] == 100
    assert len(data["products_services"]) >= 3

    # Update profile through endpoint
    updated_payload = dict(data)
    updated_payload["company_name"] = "Resilience Enterprise AI"
    updated_payload["description"] = "Penyedia solusi otomasi AI tingkat lanjut untuk industri."
    res_up = client.put("/api/v1/enterprise/profile", json=updated_payload)
    assert res_up.status_code == 200
    assert res_up.json()["status"] == "ok"

    # Verify update persisted
    res_check = client.get("/api/v1/enterprise/profile")
    assert res_check.json()["company_name"] == "Resilience Enterprise AI"


def test_strategy_calendar_generation_and_approval(client):
    res = client.get("/api/v1/strategy/calendar")
    assert res.status_code == 200
    data = res.json()
    assert data["total_items"] == 7
    items = data["items"]
    assert any(it["format"] == "video" for it in items)
    assert any(it["format"] == "carousel" for it in items)

    # Approve one item
    item_id = items[0]["id"]
    res_act = client.patch(f"/api/v1/strategy/calendar/{item_id}", json={
        "status": "approved",
        "approval_notes": "Disetujui oleh Direktur Operasional untuk jadwal Senin pagi"
    })
    assert res_act.status_code == 200
    assert res_act.json()["new_status"] == "approved"

    # Reschedule item
    res_resched = client.patch(f"/api/v1/strategy/calendar/{item_id}", json={
        "scheduled_slot": "10:30 WIB"
    })
    assert res_resched.status_code == 200

    # Verify updated state
    res2 = client.get("/api/v1/strategy/calendar")
    first_item = [i for i in res2.json()["items"] if i["id"] == item_id][0]
    assert first_item["status"] == "approved"
    assert first_item["scheduled_slot"] == "10:30 WIB"


def test_calendar_rejects_invalid_state_transitions(client):
    items = client.get("/api/v1/strategy/calendar").json()["items"]
    item_id = items[0]["id"]
    # draft -> published must not bypass approval/publication lifecycle.
    response = client.patch(f"/api/v1/strategy/calendar/{item_id}", json={"status": "published"})
    assert response.status_code == 409

    approved = client.patch(f"/api/v1/strategy/calendar/{item_id}", json={"status": "approved"})
    assert approved.status_code == 200
    published = client.patch(f"/api/v1/strategy/calendar/{item_id}", json={"status": "published"})
    assert published.status_code == 409


def test_analytics_dashboard_and_feedback_traceability(client):
    res = client.get("/api/v1/analytics/dashboard")
    assert res.status_code == 200
    data = res.json()
    summary = data["summary"]
    assert summary["total_posts_tracked"] >= 3
    assert summary["total_reach"] > 0
    assert summary["is_simulated"] is True
    assert "demo_seed_dataset" in summary["data_source"]
    assert summary["pending_ingestion"] == 0
    assert all(post["is_simulated"] is True for post in data["posts"])
    assert all(post["ingestion_status"] == "complete" for post in data["posts"])

    # Verify insights are present
    insights = data["insights"]
    assert len(insights) >= 2
    assert all("record_ids" in ins["data_points"] for ins in insights)
    assert all(ins["data_points"]["sample_size"] >= 3 for ins in insights)

    # Check that calendar item reflects insight adjustment (FEATURE-03 closed loop)
    cal_res = client.get("/api/v1/strategy/calendar")
    cal_items = cal_res.json()["items"]
    assert any(it.get("feedback_insight_id") is not None for it in cal_items)
    applied_ids = {it["feedback_insight_id"] for it in cal_items if it.get("feedback_insight_id")}
    assert applied_ids <= {ins["id"] for ins in insights}
