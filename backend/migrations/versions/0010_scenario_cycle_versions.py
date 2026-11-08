"""Permit immutable revisions of scenario plans without discarding old reviews.

Revision ID: 0010_scenario_cycle_versions
Revises: 0009_jira_checkpoint_scope
"""
from alembic import op

revision = "0010_scenario_cycle_versions"
down_revision = "0009_jira_checkpoint_scope"
branch_labels = None
depends_on = None


def _replace(old_name, new_name, new_columns):
    dialect = op.get_bind().dialect.name
    with op.batch_alter_table("scenarios", recreate="always" if dialect == "sqlite" else "auto") as batch:
        batch.drop_constraint(old_name, type_="unique")
        batch.create_unique_constraint(new_name, new_columns)


def upgrade():
    _replace("uq_scenarios_kind", "uq_scenarios_run_kind_version", ["run_id", "kind", "version"])


def downgrade():
    from sqlalchemy import text
    duplicates = op.get_bind().execute(text(
        "SELECT run_id, kind FROM scenarios GROUP BY run_id, kind HAVING COUNT(*) > 1 LIMIT 1"
    )).first()
    if duplicates:
        raise RuntimeError("Cannot downgrade with immutable scenario revisions")
    _replace("uq_scenarios_run_kind_version", "uq_scenarios_kind", ["run_id", "kind"])
