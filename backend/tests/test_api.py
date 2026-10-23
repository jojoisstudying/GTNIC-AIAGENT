import pytest
from fastapi.testclient import TestClient
from src.api import app

client = TestClient(app)

def test_health_check():
    res = client.get("/")
    assert res.status_code == 200
    assert res.json()["status"] == "online"

def test_list_layouts():
    res = client.get("/api/v1/layouts")
    assert res.status_code == 200
    data = res.json()
    assert "total" in data
    assert "layouts" in data
    assert data["total"] >= 8

def test_get_brand():
    res = client.get("/api/v1/brand")
    assert res.status_code == 200
    data = res.json()
    assert "name" in data or "brand_name" in data or "industry" in data
