"""Scheduler lock, retry/approval columns, dan sinkronisasi skema enterprise/analytics.

Revision ID: 0003_scheduler_autonomy_ingest
"""
import sqlalchemy as sa
from alembic import op

revision = "0003_scheduler_autonomy_ingest"
down_revision = "0002_analytics_publication_link"
branch_labels = None
depends_on = None

NEW_COLUMNS = {
    "publish_attempts": sa.Column("publish_attempts", sa.Integer(), nullable=False, server_default="0"),
    "next_attempt_at": sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
    "last_error": sa.Column("last_error", sa.Text(), nullable=True),
    "approved_by": sa.Column("approved_by", sa.String(64), nullable=True),
}


def upgrade() -> None:
    from src.core.db import Base
    bind = op.get_bind()
    # Melengkapi tabel yang belum pernah dimigrasi (enterprise_profiles, content_strategy_items,
    # post_analytics, analytics_insights, scheduler_locks, dst). checkfirst: tabel ada dilewati.
    Base.metadata.create_all(bind=bind, checkfirst=True)
    insp = sa.inspect(bind)
    existing = {c["name"] for c in insp.get_columns("content_strategy_items")}
    for name, col in NEW_COLUMNS.items():
        if name not in existing:
            op.add_column("content_strategy_items", col)


def downgrade() -> None:
    with op.batch_alter_table("content_strategy_items") as batch:
        for name in NEW_COLUMNS:
            batch.drop_column(name)
    op.drop_table("scheduler_locks")
