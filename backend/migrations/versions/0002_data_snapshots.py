"""P1-01 aggregate snapshots.

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('data_snapshots',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.String(128), nullable=False),
        sa.Column('team_id', sa.String(128), nullable=False),
        sa.Column('snapshot_id', sa.String(128), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.UniqueConstraint('tenant_id', 'team_id', 'snapshot_id', name='uq_data_snapshot_scope'))
    op.create_index('ix_data_snapshots_tenant_id', 'data_snapshots', ['tenant_id'])
    op.create_index('ix_data_snapshots_team_id', 'data_snapshots', ['team_id'])

def downgrade():
    op.drop_index('ix_data_snapshots_team_id', table_name='data_snapshots')
    op.drop_index('ix_data_snapshots_tenant_id', table_name='data_snapshots')
    op.drop_table('data_snapshots')
