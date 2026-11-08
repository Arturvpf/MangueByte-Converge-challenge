"""Remove SQLite's hidden rowid from the append-only audit table.

Revision ID: 0004a
Revises: 0004
"""
import re

from alembic import op

revision = "0004a"
down_revision = "0004"
branch_labels = None
depends_on = None


def _rebuild(without_rowid):
    # Preserve the existing table definition, explicit indexes and triggers. A
    # rowid table cannot distinguish an omitted rowid from an explicit -1 in
    # BEFORE INSERT, so it cannot safely guard every REPLACE with a trigger.
    conn = op.get_bind()
    sql = conn.exec_driver_sql("SELECT sql FROM sqlite_master WHERE type='table' AND name='audit_events'").scalar_one()
    objects = conn.exec_driver_sql("SELECT sql FROM sqlite_master WHERE tbl_name='audit_events' "
                                   "AND type IN ('index', 'trigger') AND sql IS NOT NULL ORDER BY type, name").scalars().all()
    columns = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(audit_events)")]
    quoted = ', '.join('"' + name.replace('"', '""') + '"' for name in columns)
    sql = re.sub(r'^CREATE TABLE\s+(?:"audit_events"|audit_events)',
                 'CREATE TABLE audit_events_rebuild', sql, count=1, flags=re.IGNORECASE)
    if without_rowid:
        sql += ' WITHOUT ROWID'
    else:
        sql = re.sub(r'\s+WITHOUT ROWID\s*$', '', sql, flags=re.IGNORECASE)
    conn.exec_driver_sql(sql)
    conn.exec_driver_sql(f'INSERT INTO audit_events_rebuild ({quoted}) SELECT {quoted} FROM audit_events')
    conn.exec_driver_sql('DROP TABLE audit_events')
    conn.exec_driver_sql('ALTER TABLE audit_events_rebuild RENAME TO audit_events')
    for statement in objects:
        conn.exec_driver_sql(statement)


def upgrade():
    if op.get_bind().dialect.name == "sqlite":
        _rebuild(True)


def downgrade():
    if op.get_bind().dialect.name == "sqlite":
        _rebuild(False)
