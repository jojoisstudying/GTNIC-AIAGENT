"""Add publishing_mode to automation_settings and enterprise_profiles.

Revision ID: 0008_publishing_modes
down_revision: 0007_publication_workflow_automation

"""
revision = "0008_publishing_modes"
down_revision = "0007_publication_workflow_automation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    import sqlalchemy as sa
    from alembic import op

    bind = op.get_bind()
    insp = sa.inspect(bind)

    if insp.has_table("automation_settings"):
        cols = {c["name"] for c in insp.get_columns("automation_settings")}
        if "publishing_mode" not in cols:
            op.add_column(
                "automation_settings",
                sa.Column("publishing_mode", sa.String(32), nullable=False, server_default="autopilot"),
            )
            op.execute("UPDATE automation_settings SET publishing_mode = 'autopilot' WHERE publishing_mode IS NULL OR publishing_mode = ''")

    if insp.has_table("enterprise_profiles"):
        cols = {c["name"] for c in insp.get_columns("enterprise_profiles")}
        if "publishing_mode" not in cols:
            op.add_column(
                "enterprise_profiles",
                sa.Column("publishing_mode", sa.String(32), nullable=False, server_default="autopilot"),
            )
            op.execute("UPDATE enterprise_profiles SET publishing_mode = 'autopilot' WHERE publishing_mode IS NULL OR publishing_mode = ''")


def downgrade() -> None:
    pass
