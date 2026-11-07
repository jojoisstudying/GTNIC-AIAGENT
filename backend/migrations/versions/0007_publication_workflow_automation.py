"""Publication approval workflow, automation center, analytics history.

Revision ID: 0007_publication_workflow_automation
down_revision: 0006_approvals_integrations_metrics

Menambah (tanpa menghapus data):
- publications: kolom alur persetujuan (platform, dedupe_key, approved_*, media_type,
  hashtags_json, publish_attempts, claim_token/claimed_at, updated_at, strategy_item_id)
- tabel automation_settings / automation_events (Pusat Otomatisasi)
- tabel post_analytics_snapshots (riwayat metrik per konten)

Semua langkah idempotent supaya aman dijalankan pada database yang sudah ada.
"""
revision = "0007_publication_workflow_automation"
down_revision = "0006_approvals_integrations_metrics"
branch_labels = None
depends_on = None


PUBLICATION_COLUMNS = (
    ("strategy_item_id", lambda sa: sa.Column("strategy_item_id", sa.Integer(), nullable=True)),
    ("platform", lambda sa: sa.Column("platform", sa.String(16), nullable=False, server_default="instagram")),
    ("dedupe_key", lambda sa: sa.Column("dedupe_key", sa.String(128), nullable=True)),
    ("approved_at", lambda sa: sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True)),
    ("approved_by", lambda sa: sa.Column("approved_by", sa.String(64), nullable=True)),
    ("media_type", lambda sa: sa.Column("media_type", sa.String(32), nullable=True)),
    ("hashtags_json", lambda sa: sa.Column("hashtags_json", sa.Text(), nullable=True)),
    ("publish_attempts", lambda sa: sa.Column("publish_attempts", sa.Integer(), nullable=False, server_default="0")),
    ("claim_token", lambda sa: sa.Column("claim_token", sa.String(64), nullable=True)),
    ("claimed_at", lambda sa: sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True)),
    ("updated_at", lambda sa: sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True)),
)


def upgrade() -> None:
    import sqlalchemy as sa
    from alembic import op
    from src.core.db import Base

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)
    insp = sa.inspect(bind)

    existing = {c["name"] for c in insp.get_columns("publications")}
    for name, factory in PUBLICATION_COLUMNS:
        if name not in existing:
            op.add_column("publications", factory(sa))

    # Backfill: baris publikasi lama dianggap sudah disetujui (sudah melewati gerbang manusia).
    op.execute("UPDATE publications SET updated_at = created_at WHERE updated_at IS NULL")
    op.execute("UPDATE publications SET platform = 'instagram' WHERE platform IS NULL OR platform = ''")
    op.execute("UPDATE publications SET publish_attempts = 0 WHERE publish_attempts IS NULL")

    indexes = {ix["name"] for ix in insp.get_indexes("publications")}
    if "ix_publications_dedupe_key" not in indexes:
        op.create_index("ix_publications_dedupe_key", "publications", ["dedupe_key"], unique=True)


def downgrade() -> None:
    from alembic import op
    op.drop_index("ix_publications_dedupe_key", table_name="publications")
    with op.batch_alter_table("publications") as batch:
        for name, _factory in reversed(PUBLICATION_COLUMNS):
            batch.drop_column(name)
    op.drop_table("post_analytics_snapshots")
    op.drop_table("automation_events")
    op.drop_table("automation_settings")
