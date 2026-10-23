"""Create pipeline tables and expand legacy assets without dropping data."""
from alembic import op
import sqlalchemy as sa

from src.core.db import Base


revision = "0001_pipeline_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the defined schema and preserve/upgrade any preexisting assets table."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # Creating from model metadata skips existing tables; legacy assets is migrated below.
    Base.metadata.create_all(bind=bind)
    if "assets" not in existing_tables:
        return

    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("assets")}
    additions = {
        "status": sa.Column("status", sa.String(32), nullable=False, server_default="approved"),
        "person_id": sa.Column("person_id", sa.String(128), nullable=True),
        "source_path": sa.Column("source_path", sa.Text(), nullable=True),
        "model": sa.Column("model", sa.Text(), nullable=True),
        "prompt": sa.Column("prompt", sa.Text(), nullable=True),
        "cache_key": sa.Column("cache_key", sa.String(64), nullable=True),
        "created_at": sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        "run_id": sa.Column("run_id", sa.String(32), nullable=True),
        "sha256": sa.Column("sha256", sa.String(64), nullable=True),
        "kind": sa.Column("kind", sa.String(32), nullable=True),
    }
    for name, column in additions.items():
        if name not in existing_columns:
            op.add_column("assets", column)

    # Existing manual assets and placeholders remain usable and are approved by default.
    op.execute(sa.text("UPDATE assets SET status = 'approved' WHERE status IS NULL"))
    op.execute(sa.text("UPDATE assets SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))

    inspector = sa.inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes("assets")}
    if "idx_assets_cache_key" not in indexes:
        op.create_index("idx_assets_cache_key", "assets", ["cache_key"], unique=True,
                        sqlite_where=sa.text("cache_key IS NOT NULL"))


def downgrade() -> None:
    """Drop pipeline tables; retain assets and its metadata to avoid destructive downgrade."""
    bind = op.get_bind()
    for table_name in (
        "credentials_status", "publications", "events", "designs", "plans",
        "research_snapshots", "runs",
    ):
        if table_name in sa.inspect(bind).get_table_names():
            op.drop_table(table_name)
