"""Tabel notifications dan audit_log.

Revision ID: 0004_notifications_audit
"""
revision = "0004_notifications_audit"
down_revision = "0003_scheduler_autonomy_ingest"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from alembic import op
    from src.core.db import Base
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    from alembic import op
    op.drop_table("audit_log")
    op.drop_table("notifications")
