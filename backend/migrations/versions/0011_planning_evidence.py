"""Add versioned replan evidence, outcomes and source-level collection checkpoints."""
from alembic import op
import sqlalchemy as sa

revision = "0011_planning_evidence"
down_revision = "0010_scenario_cycle_versions"
branch_labels = None
depends_on = None


def _replace_import_source_constraint(kinds):
    sqlite = op.get_bind().dialect.name == "sqlite"
    with op.batch_alter_table("data_imports", recreate="always" if sqlite else "auto") as batch:
        batch.drop_constraint("ck_imports_source", type_="check")
        batch.create_check_constraint("ck_imports_source", f"source_kind IN ({kinds})")


def upgrade():
    _replace_import_source_constraint("'csv', 'jira', 'synthetic'")
    op.create_table(
        "planning_evidence",
        sa.Column("run_id", sa.String(36), primary_key=True),
        sa.Column("idempotency_key", sa.String(128), primary_key=True),
        sa.Column("actor_user_id", sa.String(36), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "decision_observations",
        sa.Column("decision_id", sa.String(36), primary_key=True),
        sa.Column("week_start", sa.String(10), primary_key=True),
        sa.Column("actor_user_id", sa.String(36), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "jira_collection",
        sa.Column("tenant_id", sa.String(128), primary_key=True),
        sa.Column("team_id", sa.String(128), primary_key=True),
        sa.Column("source_key", sa.String(64), primary_key=True),
        sa.Column("snapshot_id", sa.String(128)),
        sa.Column("last_success", sa.DateTime(timezone=True)),
    )


def downgrade():
    has_synthetic = op.get_bind().execute(sa.text(
        "SELECT 1 FROM data_imports WHERE source_kind = 'synthetic' LIMIT 1"
    )).first()
    if has_synthetic:
        raise RuntimeError("Cannot downgrade with synthetic imports")
    _replace_import_source_constraint("'csv', 'jira'")
    op.drop_table("jira_collection")
    op.drop_table("decision_observations")
    op.drop_table("planning_evidence")
