"""SQLAlchemy models and session configuration for persistent pipeline data."""
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from src import config


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base class for database models."""


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    brand_id: Mapped[str | None] = mapped_column(String(128))
    enterprise_profile_id: Mapped[int | None] = mapped_column(Integer)
    enterprise_profile_version: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class ResearchSnapshot(Base):
    __tablename__ = "research_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), nullable=False, index=True)
    data_json: Mapped[str] = mapped_column(Text, nullable=False)
    warnings_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    ok: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class Plan(Base):
    __tablename__ = "plans"
    __table_args__ = (UniqueConstraint("run_id", "version", name="uq_plans_run_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    ok: Mapped[bool] = mapped_column(nullable=False, default=False)
    plan_json: Mapped[str] = mapped_column(Text, nullable=False)
    issues_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class Design(Base):
    __tablename__ = "designs"
    __table_args__ = (UniqueConstraint("run_id", "version", name="uq_designs_run_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), nullable=False, index=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("plans.id"))
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    ok: Mapped[bool] = mapped_column(nullable=False, default=False)
    result_json: Mapped[str] = mapped_column(Text, nullable=False)
    preview_path: Mapped[str | None] = mapped_column(Text)
    semantic_qc_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    tags: Mapped[str] = mapped_column(Text, nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="approved")
    person_id: Mapped[str | None] = mapped_column(String(128))
    source_path: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    prompt: Mapped[str | None] = mapped_column(Text)
    cache_key: Mapped[str | None] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("runs.id"))
    sha256: Mapped[str | None] = mapped_column(String(64))
    kind: Mapped[str | None] = mapped_column(String(32))


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("runs.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    step: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    target: Mapped[str | None] = mapped_column(Text)
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    units: Mapped[float | None] = mapped_column(Float)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    duration_ms: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ok")
    detail_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class Publication(Base):
    __tablename__ = "publications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("runs.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    intent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    media_id: Mapped[str | None] = mapped_column(String(128))
    permalink: Mapped[str | None] = mapped_column(Text)
    caption: Mapped[str] = mapped_column(Text, nullable=False, default="")
    image_urls_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class CredentialStatus(Base):
    __tablename__ = "credentials_status"

    provider: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    alerted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)



class EnterpriseProfile(Base):
    __tablename__ = "enterprise_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_name: Mapped[str] = mapped_column(String(128), nullable=False)
    industry: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    products_services_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    target_audience_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    business_goals_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    tone: Mapped[str] = mapped_column(String(128), nullable=False, default="profesional, terpercaya")
    content_pillars_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    brand_rules_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    contact_info_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    approval_workflow_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    operating_preferences_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    completeness_score: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class EnterpriseProfileVersion(Base):
    __tablename__ = "enterprise_profile_versions"
    __table_args__ = (UniqueConstraint("profile_id", "version", name="uq_enterprise_profile_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("enterprise_profiles.id"), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class ContentStrategyItem(Base):
    __tablename__ = "content_strategy_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_date: Mapped[str] = mapped_column(String(32), nullable=False)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    format: Mapped[str] = mapped_column(String(32), nullable=False, default="carousel")  # carousel | video
    content_pillar: Mapped[str] = mapped_column(String(128), nullable=False)
    objective: Mapped[str] = mapped_column(String(128), nullable=False)
    target_segment: Mapped[str] = mapped_column(String(128), nullable=False, default="Umum")
    scheduled_slot: Mapped[str] = mapped_column(String(64), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    # status: draft | awaiting_approval | approved | scheduled | publishing | published | rejected
    approval_notes: Mapped[str | None] = mapped_column(Text)
    run_id: Mapped[str | None] = mapped_column(String(32), index=True)
    feedback_insight_id: Mapped[int | None] = mapped_column(Integer, index=True)
    campaign_id: Mapped[int | None] = mapped_column(Integer, index=True)
    publish_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[str | None] = mapped_column(String(64))  # api_user | autonomy_policy | None
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class PostAnalytics(Base):
    __tablename__ = "post_analytics"
    __table_args__ = (UniqueConstraint("publication_id", name="uq_post_analytics_publication"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    publication_id: Mapped[int | None] = mapped_column(ForeignKey("publications.id"))
    run_id: Mapped[str | None] = mapped_column(String(32), index=True)
    strategy_item_id: Mapped[int | None] = mapped_column(Integer, index=True)
    media_id: Mapped[str | None] = mapped_column(String(128))
    permalink: Mapped[str | None] = mapped_column(Text)
    format: Mapped[str] = mapped_column(String(32), nullable=False)
    content_pillar: Mapped[str] = mapped_column(String(128), nullable=False)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    reach: Mapped[int | None] = mapped_column(Integer)
    impressions: Mapped[int | None] = mapped_column(Integer)
    likes: Mapped[int | None] = mapped_column(Integer)
    comments: Mapped[int | None] = mapped_column(Integer)
    shares: Mapped[int | None] = mapped_column(Integer)
    saves: Mapped[int | None] = mapped_column(Integer)
    profile_visits: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="instagram_api")
    is_simulated: Mapped[bool] = mapped_column(nullable=False, default=False)
    ingestion_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    data_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class SchedulerLock(Base):
    """Lock leader agar hanya satu proses/worker yang menjalankan scheduler."""
    __tablename__ = "scheduler_locks"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    objective: Mapped[str] = mapped_column(String(128), nullable=False)
    target_audience: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    start_date: Mapped[str] = mapped_column(String(16), nullable=False)  # YYYY-MM-DD
    end_date: Mapped[str] = mapped_column(String(16), nullable=False)
    products_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_requirements: Mapped[str] = mapped_column(Text, nullable=False, default="")
    performance_targets_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")  # draft|active|completed|cancelled
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="info")  # info|warning|error
    entity_type: Mapped[str | None] = mapped_column(String(48))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    is_read: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor: Mapped[str] = mapped_column(String(64), nullable=False, default="system")
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(48), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(64))
    detail_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


NEW_COLUMNS = {
    "content_strategy_items": {
        "publish_attempts": "INTEGER NOT NULL DEFAULT 0",
        "next_attempt_at": "DATETIME",
        "last_error": "TEXT",
        "approved_by": "VARCHAR(64)",
        "campaign_id": "INTEGER",
    },
}


def ensure_schema(bind) -> None:
    """Buat tabel yang belum ada dan tambahkan kolom baru pada tabel lama (idempotent)."""
    Base.metadata.create_all(bind)
    insp = inspect(bind)
    for table, cols in NEW_COLUMNS.items():
        if not insp.has_table(table):
            continue
        existing = {c["name"] for c in insp.get_columns(table)}
        missing = {n: d for n, d in cols.items() if n not in existing}
        if missing:
            with bind.begin() as conn:
                for name, ddl in missing.items():
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def ingest_publication_metrics(session, publication: Publication, metrics: dict[str, Any], *,
                               source: str, collected_at: datetime | None = None) -> PostAnalytics:
    """Upsert platform metrics for a publication; absent measurements remain NULL."""
    row = session.query(PostAnalytics).filter_by(publication_id=publication.id).one_or_none()
    if row is None:
        row = PostAnalytics(
            publication_id=publication.id,
            run_id=publication.run_id,
            media_id=publication.media_id,
            permalink=publication.permalink,
            format=str(metrics.get("format") or "unknown"),
            content_pillar=str(metrics.get("content_pillar") or "Belum diklasifikasikan"),
            topic=str(metrics.get("topic") or ""),
        )
        session.add(row)
    metric_fields = ("reach", "impressions", "likes", "comments", "shares", "saves", "profile_visits")
    for field in metric_fields:
        value = metrics.get(field)
        setattr(row, field, int(value) if value is not None else None)
    row.source = source
    row.is_simulated = bool(metrics.get("is_simulated", False))
    row.ingestion_status = "complete" if any(metrics.get(k) is not None for k in metric_fields) else "pending"
    row.data_timestamp = collected_at or (utc_now() if row.ingestion_status == "complete" else None)
    session.flush()
    return row


class AnalyticsInsight(Base):
    __tablename__ = "analytics_insights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    observation: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[str] = mapped_column(String(32), nullable=False, default="high")  # high | medium | preliminary
    data_points_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    applied_to_strategy: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


def make_engine(url: str | None = None, **kwargs: Any) -> Engine:
    """Create an engine, ensuring the default local SQLite directory exists."""
    database_url = url or config.database_url()
    if database_url.startswith("sqlite:///") and database_url != "sqlite:///:memory:":
        db_path = Path(database_url.removeprefix("sqlite:///"))
        db_path.parent.mkdir(parents=True, exist_ok=True)
        kwargs.setdefault("connect_args", {"check_same_thread": False})
    return create_engine(database_url, future=True, **kwargs)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
