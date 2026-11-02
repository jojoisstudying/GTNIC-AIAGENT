"""Link analytics to publications and permit unknown metrics."""
from alembic import op
import sqlalchemy as sa

revision = "0002_analytics_publication_link"
down_revision = "0001_pipeline_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "enterprise_profile_versions" not in tables and "enterprise_profiles" in tables:
        op.create_table(
            "enterprise_profile_versions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("profile_id", sa.Integer(), sa.ForeignKey("enterprise_profiles.id"), nullable=False),
            sa.Column("version", sa.String(length=64), nullable=False),
            sa.Column("snapshot_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("profile_id", "version", name="uq_enterprise_profile_version"),
        )
        op.create_index("ix_enterprise_profile_versions_profile_id", "enterprise_profile_versions", ["profile_id"])
    if "publications" in tables:
        publication_columns = {column["name"] for column in sa.inspect(bind).get_columns("publications")}
        if "published_at" not in publication_columns:
            op.add_column("publications", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
        if "scheduled_for" not in publication_columns:
            op.add_column("publications", sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True))
    if "designs" in tables:
        design_columns = {column["name"] for column in sa.inspect(bind).get_columns("designs")}
        if "semantic_qc_json" not in design_columns:
            op.add_column("designs", sa.Column("semantic_qc_json", sa.Text(), nullable=True))
    if "runs" in tables:
        run_columns = {column["name"] for column in sa.inspect(bind).get_columns("runs")}
        with op.batch_alter_table("runs") as batch:
            if "enterprise_profile_id" not in run_columns:
                batch.add_column(sa.Column("enterprise_profile_id", sa.Integer(), nullable=True))
            if "enterprise_profile_version" not in run_columns:
                batch.add_column(sa.Column("enterprise_profile_version", sa.String(length=64), nullable=True))
    if "post_analytics" not in tables:
        return

    inspector = sa.inspect(bind)
    columns = {column["name"]: column for column in inspector.get_columns("post_analytics")}
    if "publication_id" not in columns:
        with op.batch_alter_table("post_analytics") as batch:
            batch.add_column(sa.Column("publication_id", sa.Integer(), nullable=True))
            batch.create_foreign_key(
                "fk_post_analytics_publication_id_publications", "publications",
                ["publication_id"], ["id"],
            )
    if "ingestion_status" not in columns:
        with op.batch_alter_table("post_analytics") as batch:
            batch.add_column(sa.Column("ingestion_status", sa.String(length=32), nullable=False, server_default="pending"))
    inspector = sa.inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes("post_analytics")}
    if "uq_post_analytics_publication" not in indexes:
        op.create_index("uq_post_analytics_publication", "post_analytics", ["publication_id"], unique=True)

    nullable_columns = {column["name"]: column for column in sa.inspect(bind).get_columns("post_analytics")}
    with op.batch_alter_table("post_analytics") as batch:
        for name in ("reach", "impressions", "likes", "comments", "shares", "saves", "profile_visits"):
            if name in nullable_columns and not nullable_columns[name]["nullable"]:
                batch.alter_column(name, existing_type=sa.Integer(), nullable=True, server_default=None)
        if "data_timestamp" in nullable_columns and not nullable_columns["data_timestamp"]["nullable"]:
            batch.alter_column("data_timestamp", existing_type=sa.DateTime(timezone=True), nullable=True,
                               server_default=None)


def downgrade() -> None:
    # Keep analytics data intact; making unknown metrics non-null would require inventing values.
    pass
