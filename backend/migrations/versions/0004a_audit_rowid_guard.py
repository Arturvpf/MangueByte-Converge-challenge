"""Guard SQLite rowid conflicts as well as the logical audit id.

Revision ID: 0004a
Revises: 0004
"""
from alembic import op

revision = "0004a"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name == "sqlite":
        op.execute("CREATE TRIGGER audit_events_no_rowid_replace BEFORE INSERT ON audit_events "
                   "WHEN EXISTS (SELECT 1 FROM audit_events WHERE rowid = NEW.rowid) "
                   "BEGIN SELECT RAISE(ABORT, 'audit events are append-only'); END")


def downgrade():
    if op.get_bind().dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS audit_events_no_rowid_replace")
