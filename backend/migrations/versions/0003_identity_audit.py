"""P2-01 identity, memberships and append-only audit events.

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None

APPEND_ONLY = 'audit events are append-only'


def upgrade():
    op.create_table('tenants',
        sa.Column('tenant_id', sa.String(128), primary_key=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('users',
        sa.Column('user_id', sa.String(36), primary_key=True),
        sa.Column('tenant_id', sa.String(128), sa.ForeignKey('tenants.tenant_id'), nullable=False),
        sa.Column('email', sa.String(320), nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('token_version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('tenant_id', 'email', name='uq_users_tenant_email'))
    op.create_index('ix_users_tenant_id', 'users', ['tenant_id'])
    op.create_table('memberships',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.String(128), sa.ForeignKey('tenants.tenant_id'), nullable=False),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.user_id'), nullable=False),
        sa.Column('role', sa.String(16), nullable=False),
        sa.Column('team_id', sa.String(128), nullable=True),
        sa.UniqueConstraint('user_id', 'role', 'team_id', name='uq_memberships_user_role_team'),
        # Mirrors permissions.check_memberships: only rh/admin may be tenant-wide (team_id NULL).
        sa.CheckConstraint("role IN ('gestor', 'rh', 'admin')", name='ck_memberships_role'),
        sa.CheckConstraint("team_id IS NOT NULL OR role IN ('rh', 'admin')", name='ck_memberships_tenant_wide_role'),
        sa.CheckConstraint("team_id IS NULL OR length(trim(team_id)) > 0", name='ck_memberships_team_nonblank'))
    op.create_index('ix_memberships_tenant_id', 'memberships', ['tenant_id'])
    op.create_index('ix_memberships_user_id', 'memberships', ['user_id'])
    op.create_table('audit_events',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('trace_id', sa.String(128), nullable=False),
        sa.Column('tenant_id', sa.String(128), nullable=False),
        sa.Column('team_id', sa.String(128), nullable=True),
        sa.Column('actor_type', sa.String(16), nullable=False),
        sa.Column('actor_user_id', sa.String(36), nullable=True),
        sa.Column('action', sa.String(64), nullable=False),
        sa.Column('outcome', sa.String(16), nullable=False),
        sa.Column('resource_type', sa.String(64), nullable=True),
        sa.Column('resource_id', sa.String(128), nullable=True),
        sa.Column('details', sa.JSON(), nullable=False))
    for column in ('occurred_at', 'trace_id', 'tenant_id', 'team_id', 'action'):
        op.create_index(f'ix_audit_events_{column}', 'audit_events', [column])

    # Database-level append-only guard, so raw SQL cannot bypass the ORM check.
    dialect = op.get_bind().dialect.name
    if dialect == 'sqlite':
        for kind in ('UPDATE', 'DELETE'):
            op.execute(f"CREATE TRIGGER audit_events_no_{kind.lower()} BEFORE {kind} ON audit_events "
                       f"BEGIN SELECT RAISE(ABORT, '{APPEND_ONLY}'); END")
    elif dialect == 'postgresql':
        op.execute("CREATE FUNCTION audit_events_append_only() RETURNS trigger LANGUAGE plpgsql AS "
                   f"$$ BEGIN RAISE EXCEPTION '{APPEND_ONLY}'; END $$")
        op.execute("CREATE TRIGGER audit_events_append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON audit_events "
                   "FOR EACH STATEMENT EXECUTE FUNCTION audit_events_append_only()")


def downgrade():
    dialect = op.get_bind().dialect.name
    if dialect == 'sqlite':
        op.execute('DROP TRIGGER IF EXISTS audit_events_no_update')
        op.execute('DROP TRIGGER IF EXISTS audit_events_no_delete')
    elif dialect == 'postgresql':
        op.execute('DROP TRIGGER IF EXISTS audit_events_append_only ON audit_events')
        op.execute('DROP FUNCTION IF EXISTS audit_events_append_only()')
    for column in ('action', 'team_id', 'tenant_id', 'trace_id', 'occurred_at'):
        op.drop_index(f'ix_audit_events_{column}', table_name='audit_events')
    op.drop_table('audit_events')
    op.drop_index('ix_memberships_user_id', table_name='memberships')
    op.drop_index('ix_memberships_tenant_id', table_name='memberships')
    op.drop_table('memberships')
    op.drop_index('ix_users_tenant_id', table_name='users')
    op.drop_table('users')
    op.drop_table('tenants')
