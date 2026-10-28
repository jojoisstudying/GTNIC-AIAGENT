"""Tests for publishing idempotency, intent status, and pending intent blocking."""
from datetime import datetime, timezone
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from src.carousel.agents import publisher
from src.core.db import Base, Publication


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sm = sessionmaker(bind=engine)
    return sm


def test_publish_creates_intent_and_published(monkeypatch, test_db):
    session = test_db()

    # Mock hosting and instagram
    monkeypatch.setattr("src.carousel.tools.hosting.upload_jpeg", lambda p, http=None: f"https://cdn.example.com/{p}")
    monkeypatch.setattr("src.carousel.tools.instagram.publish_carousel", lambda urls, cap, ctx=None: "ig_media_123")
    monkeypatch.setattr("src.carousel.tools.instagram.get_media_metrics", lambda mid, ctx=None: {"permalink": "https://instagr.am/p/123"})

    class MockContext:
        def __init__(self, s):
            self.session = s
            self.run_id = "run-test-123"
            self.http = None
            self.events = []
        def emit(self, kind, name, **fields):
            self.events.append((kind, name, fields))

    ctx = MockContext(session)
    plan = {"caption": "Test Caption", "hashtags": ["#agent", "#ig"]}
    slide_paths = ["slide1.jpg", "slide2.jpg"]

    res = publisher.publish(plan, slide_paths, on_step=lambda *_: None, ctx=ctx)
    assert res["media_id"] == "ig_media_123"
    assert res["permalink"] == "https://instagr.am/p/123"

    # Check publication in DB
    pub = session.scalar(select(Publication).where(Publication.run_id == "run-test-123"))
    assert pub is not None
    assert pub.status == "published"
    assert pub.media_id == "ig_media_123"
    assert pub.permalink == "https://instagr.am/p/123"
    assert "slide1.jpg" in pub.image_urls_json


def test_publish_blocks_when_pending_intent_exists(monkeypatch, test_db):
    session = test_db()

    # Insert a hanging intent
    hanging = Publication(
        run_id="run-old",
        status="intent",
        intent_at=datetime.now(timezone.utc),
        caption="hanging post"
    )
    session.add(hanging)
    session.commit()

    class MockContext:
        def __init__(self, s):
            self.session = s
            self.run_id = "run-new"
            self.http = None

    ctx = MockContext(session)
    plan = {"caption": "New Caption"}

    with pytest.raises(publisher.PendingIntentError) as excinfo:
        publisher.publish(plan, ["s1.jpg"], on_step=lambda *_: None, ctx=ctx)
    assert "intent menggantung" in str(excinfo.value)


def test_publish_records_failure_on_exception(monkeypatch, test_db):
    session = test_db()

    monkeypatch.setattr("src.carousel.tools.hosting.upload_jpeg", lambda p, http=None: "https://cdn.example.com/s.jpg")
    def fail_publish(*args, **kwargs):
        raise RuntimeError("Instagram API Network Error")
    monkeypatch.setattr("src.carousel.tools.instagram.publish_image", fail_publish)

    class MockContext:
        def __init__(self, s):
            self.session = s
            self.run_id = "run-fail"
            self.http = None
            self.events = []
        def emit(self, kind, name, **fields):
            self.events.append((kind, name, fields))

    ctx = MockContext(session)
    plan = {"caption": "Fail Caption"}

    with pytest.raises(RuntimeError):
        publisher.publish(plan, ["s1.jpg"], on_step=lambda *_: None, ctx=ctx)

    pub = session.scalar(select(Publication).where(Publication.run_id == "run-fail"))
    assert pub is not None
    assert pub.status == "failed"
    assert "Instagram API Network Error" in pub.error
