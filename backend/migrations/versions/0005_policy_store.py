"""P2-02 policy store.

Revision ID: 0005
Revises: 0004

source_kind is varchar(32): politica_interna does not fit in 16 characters.
"""
from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('policies',
        sa.Column('policy_id', sa.String(36), primary_key=True),
        sa.Column('tenant_id', sa.String(128), sa.ForeignKey('tenants.tenant_id'), nullable=False),
        sa.Column('rule_key', sa.String(64), nullable=False),
        sa.Column('category', sa.String(32), nullable=False),
        sa.Column('team_id', sa.String(128), nullable=True),
        sa.Column('employee_category', sa.String(64), nullable=True),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('created_by', sa.String(36), sa.ForeignKey('users.user_id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('tenant_id', 'rule_key', 'team_id', 'employee_category', name='uq_policies_scope'))
    op.create_index('ix_policies_tenant_id', 'policies', ['tenant_id'])
    op.create_index('ix_policies_rule_key', 'policies', ['rule_key'])
    op.create_index('ix_policies_team_id', 'policies', ['team_id'])
    op.create_table('policy_versions',
        sa.Column('version_id', sa.String(36), primary_key=True),
        sa.Column('policy_id', sa.String(36), sa.ForeignKey('policies.policy_id'), nullable=False),
        sa.Column('tenant_id', sa.String(128), sa.ForeignKey('tenants.tenant_id'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('parameters', sa.JSON(), nullable=False),
        sa.Column('source_kind', sa.String(32), nullable=False),
        sa.Column('source_reference', sa.String(500), nullable=False),
        sa.Column('valid_from', sa.Date(), nullable=False),
        sa.Column('valid_until', sa.Date(), nullable=True),
        sa.Column('content_hash', sa.String(64), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('author_user_id', sa.String(36), sa.ForeignKey('users.user_id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('submitted_by', sa.String(36), sa.ForeignKey('users.user_id'), nullable=True),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('approved_by', sa.String(36), sa.ForeignKey('users.user_id'), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('legal_review_reference', sa.String(500), nullable=True),
        sa.Column('review_note', sa.String(1000), nullable=True),
        sa.Column('revoked_by', sa.String(36), sa.ForeignKey('users.user_id'), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revocation_reason', sa.String(1000), nullable=True),
        sa.Column('idempotency_key', sa.String(128), nullable=True),
        sa.UniqueConstraint('policy_id', 'version', name='uq_policy_versions_number'),
        sa.UniqueConstraint('policy_id', 'idempotency_key', name='uq_policy_versions_idempotency'),
        sa.CheckConstraint("status IN ('draft', 'in_review', 'approved', 'revoked')", name='ck_policy_versions_status'),
        sa.CheckConstraint('version > 0', name='ck_policy_versions_version'),
        sa.CheckConstraint('revision >= 0', name='ck_policy_versions_revision'),
        sa.CheckConstraint('valid_until IS NULL OR valid_until > valid_from', name='ck_policy_versions_validity'),
        sa.CheckConstraint(
            "source_kind IN ('lei', 'emenda', 'cct', 'act', 'politica_interna', 'sintetico')",
            name='ck_policy_versions_source_kind'),
        sa.CheckConstraint('length(content_hash) = 64', name='ck_policy_versions_hash'))
    op.create_index('ix_policy_versions_policy_id', 'policy_versions', ['policy_id'])
    op.create_index('ix_policy_versions_tenant_id', 'policy_versions', ['tenant_id'])


def downgrade():
    op.drop_index('ix_policy_versions_tenant_id', table_name='policy_versions')
    op.drop_index('ix_policy_versions_policy_id', table_name='policy_versions')
    op.drop_table('policy_versions')
    op.drop_index('ix_policies_team_id', table_name='policies')
    op.drop_index('ix_policies_rule_key', table_name='policies')
    op.drop_index('ix_policies_tenant_id', table_name='policies')
    op.drop_table('policies')
