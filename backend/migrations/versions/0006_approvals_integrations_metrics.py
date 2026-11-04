"""Tabel approvals + enterprise_integrations; kolom metrik tambahan post_analytics.

Revision ID: 0006_approvals_integrations_metrics
"""
revision = "0006_approvals_integrations_metrics"
down_revision = "0005_campaigns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    import sqlalchemy as sa
    from alembic import op
    from src.core.db import Base
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)
    cols = {c["name"] for c in sa.inspect(bind).get_columns("post_analytics")}
    for name, typ in (("follower_delta", sa.Integer()), ("link_clicks", sa.Integer()), ("engagement_rate", sa.Float())):
        if name not in cols:
            op.add_column("post_analytics", sa.Column(name, typ, nullable=True))
