"""Tabel campaigns + kolom campaign_id pada content_strategy_items.

Revision ID: 0005_campaigns
"""
revision = "0005_campaigns"
down_revision = "0004_notifications_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    import sqlalchemy as sa
    from alembic import op
    from src.core.db import Base
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)
    cols = {c["name"] for c in sa.inspect(bind).get_columns("content_strategy_items")}
    if "campaign_id" not in cols:
        op.add_column("content_strategy_items", sa.Column("campaign_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    from alembic import op
    with op.batch_alter_table("content_strategy_items") as b:
        b.drop_column("campaign_id")
    op.drop_table("campaigns")
