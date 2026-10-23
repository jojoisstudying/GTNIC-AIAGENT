"""Tests for Instagram content_publishing_limit quota checks before publishing."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.agents import publisher
from src.core.db import Base


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sm = sessionmaker(bind=engine)
    return sm


def test_check_publishing_quota_passes_when_under_limit(monkeypatch):
    monkeypatch.setattr(
        "src.tools.instagram.get_content_publishing_limit",
        lambda ctx=None: {"quota_usage": 5, "config": {"quota_total": 25, "quota_duration": 86400}}
    )
    res = publisher.check_publishing_quota()
    assert res["quota_usage"] == 5


def test_check_publishing_quota_blocks_when_limit_reached(monkeypatch):
    monkeypatch.setattr(
        "src.tools.instagram.get_content_publishing_limit",
        lambda ctx=None: {"quota_usage": 25, "config": {"quota_total": 25, "quota_duration": 86400}}
    )
    with pytest.raises(publisher.QuotaExceededError) as excinfo:
        publisher.check_publishing_quota()
    assert "Kuota posting Instagram habis" in str(excinfo.value)
    assert "25/25" in str(excinfo.value)


def test_preflight_reports_quota_exceeded(monkeypatch, test_db):
    session = test_db()
    monkeypatch.setattr("src.config.opt", lambda k, default="": "val" if k in publisher.REQUIRED_ENV else default)
    monkeypatch.setattr(
        "src.tools.instagram.get_content_publishing_limit",
        lambda ctx=None: {"quota_usage": 50, "config": {"quota_total": 50, "quota_duration": 86400}}
    )

    plan_out = {"ok": True, "plan": {"caption": "hello"}}
    design = {"ok": True, "slides": [{"index": 1, "path": __file__}]}

    problems = publisher.preflight(plan_out, design, session=session)
    assert any("Kuota posting Instagram habis" in p for p in problems)


def test_publish_blocks_when_quota_exceeded(monkeypatch, test_db):
    session = test_db()
    monkeypatch.setattr("src.config.opt", lambda k, default="": "val" if k in publisher.REQUIRED_ENV else default)
    monkeypatch.setattr("src.core.credentials.ensure_instagram_credentials", lambda *a, **k: None)
    monkeypatch.setattr(
        "src.tools.instagram.get_content_publishing_limit",
        lambda ctx=None: {"quota_usage": 25, "config": {"quota_total": 25, "quota_duration": 86400}}
    )

    class MockContext:
        def __init__(self, s):
            self.session = s
            self.run_id = "run-quota"
            self.http = None
        def emit(self, *a, **k):
            pass

    ctx = MockContext(session)
    plan = {"caption": "Test"}
    with pytest.raises(publisher.QuotaExceededError):
        publisher.publish(plan, ["s1.jpg"], ctx=ctx)
