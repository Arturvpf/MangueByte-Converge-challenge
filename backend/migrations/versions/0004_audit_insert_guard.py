"""Block audit overwrite through INSERT OR REPLACE / upsert.

SQLite resolves REPLACE by deleting the conflicting row without firing DELETE
triggers (recursive_triggers is off by default), so 0003 did not stop it. A
BEFORE INSERT trigger rejects any insert that reuses an existing id. In
PostgreSQL there is no REPLACE; INSERT ... ON CONFLICT DO UPDATE already fires
the statement-level UPDATE trigger from 0003.

Revision ID: 0004
Revises: 0003
"""
from alembic import op

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name == 'sqlite':
        op.execute("CREATE TRIGGER audit_events_no_replace BEFORE INSERT ON audit_events "
                   "WHEN EXISTS (SELECT 1 FROM audit_events WHERE id = NEW.id) "
                   "BEGIN SELECT RAISE(ABORT, 'audit events are append-only'); END")


def downgrade():
    if op.get_bind().dialect.name == 'sqlite':
        op.execute('DROP TRIGGER IF EXISTS audit_events_no_replace')
