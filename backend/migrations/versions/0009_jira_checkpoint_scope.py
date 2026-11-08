"""Scope Jira checkpoints correctly, retaining ambiguous historic rows for audit.

Revision ID: 0009_jira_checkpoint_scope
Revises: 0008_scenario_families

Historical checkpoints had no team or source. They cannot be migrated to
an authorized team without guessing. Preserve them in a legacy table, but
never consult them for authorization or idempotency.
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_jira_checkpoint_scope"
down_revision = "0008_scenario_families"
branch_labels = None
depends_on = None


def upgrade():
    op.rename_table("jira_checkpoints", "jira_checkpoints_legacy_unscoped")
    op.create_table(
        "jira_checkpoints",
        sa.Column("tenant_id", sa.String(128), primary_key=True),
        sa.Column("team_id", sa.String(128), primary_key=True),
        sa.Column("source_key", sa.String(200), primary_key=True),
        sa.Column("issue_id", sa.String(64), primary_key=True),
        sa.Column("snapshot_id", sa.String(128), nullable=False),
    )


def downgrade():
    count = op.get_bind().execute(sa.text("SELECT count(*) FROM jira_checkpoints")).scalar_one()
    if count:
        raise RuntimeError("Cannot downgrade: scoped Jira checkpoints must be preserved")
    op.drop_table("jira_checkpoints")
    op.rename_table("jira_checkpoints_legacy_unscoped", "jira_checkpoints")
