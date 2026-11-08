"""PRD v4.2: add temporary and redesign scenario families.

Revision ID: 0008_scenario_families
Revises: 0007_merge_p1_p2
"""
from alembic import op
from sqlalchemy import text

revision = "0008_scenario_families"
down_revision = "0007_merge_p1_p2"
branch_labels = None
depends_on = None

OLD = "kind IN ('hire', 'reallocate', 'do_nothing')"
NEW = "kind IN ('hire', 'temporary', 'reallocate', 'redesign', 'do_nothing')"


def _apply(expression):
    # SQLite cannot DROP CHECK directly; named constraints are carried through
    # a reflected batch table rebuild. PostgreSQL changes only the constraint.
    recreate = "always" if op.get_bind().dialect.name == "sqlite" else "auto"
    with op.batch_alter_table("scenarios", recreate=recreate) as batch:
        batch.drop_constraint("ck_scenarios_kind", type_="check")
        batch.create_check_constraint("ck_scenarios_kind", expression)


def upgrade():
    _apply(NEW)


def downgrade():
    # Do not silently discard v4.2 decisions or scenarios.
    count = op.get_bind().execute(text(
        "SELECT count(*) FROM scenarios WHERE kind NOT IN ('hire', 'reallocate', 'do_nothing')"
    )).scalar_one()
    if count:
        raise RuntimeError("Cannot downgrade: v4.2 scenarios must be retained")
    _apply(OLD)
