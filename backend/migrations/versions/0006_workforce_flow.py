"""Pilot flow tables: imports, metrics, investigations, scenarios and decisions.

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "data_imports",
        sa.Column("import_id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("team_id", sa.String(128), nullable=False),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("source_kind", sa.String(16), nullable=False),
        sa.Column("source_reference", sa.String(200), nullable=False),
        sa.Column("snapshot_id", sa.String(128)),
        sa.Column("errors", sa.JSON(), nullable=False),
        sa.Column("history", sa.JSON(), nullable=False),
        sa.Column("aggregates", sa.JSON(), nullable=False),
        sa.Column("preview", sa.JSON(), nullable=False),
        sa.Column("line_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "team_id", "content_hash", name="uq_imports_hash"),
        sa.CheckConstraint("status IN ('invalid', 'ready', 'complete')", name="ck_imports_status"),
        sa.CheckConstraint("source_kind IN ('csv', 'jira')", name="ck_imports_source"),
    )
    op.create_index("ix_data_imports_tenant_id", "data_imports", ["tenant_id"])
    op.create_table(
        "metric_results",
        sa.Column("metric_id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("team_id", sa.String(128), nullable=False),
        sa.Column("snapshot_id", sa.String(128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "team_id", "snapshot_id", name="uq_metrics_snapshot"),
    )
    op.create_index("ix_metric_results_tenant_id", "metric_results", ["tenant_id"])
    op.create_table(
        "forecast_results",
        sa.Column("forecast_id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("team_id", sa.String(128), nullable=False),
        sa.Column("snapshot_id", sa.String(128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "team_id", "snapshot_id", name="uq_forecast_snapshot"),
    )
    op.create_index("ix_forecast_results_tenant_id", "forecast_results", ["tenant_id"])
    op.create_table(
        "investigation_runs",
        sa.Column("run_id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("team_id", sa.String(128), nullable=False),
        sa.Column("snapshot_id", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("cycle_count", sa.Integer(), nullable=False),
        sa.Column("cycle_limit", sa.Integer(), nullable=False),
        sa.Column("trace_id", sa.String(32), nullable=False),
        sa.Column("failure", sa.String(64)),
        sa.Column("report", sa.JSON()),
        sa.Column("forecast", sa.JSON()),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "team_id", "idempotency_key", name="uq_runs_idempotency"),
        sa.CheckConstraint("cycle_count >= 0 AND cycle_limit > 0 AND version >= 0", name="ck_runs_counts"),
    )
    op.create_index("ix_investigation_runs_tenant_id", "investigation_runs", ["tenant_id"])
    op.create_table(
        "investigation_answers",
        sa.Column("answer_id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("question_id", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("answer", sa.String(2000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "question_id", name="uq_answers_question"),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_answers_key"),
    )
    op.create_index("ix_investigation_answers_run_id", "investigation_answers", ["run_id"])
    op.create_table(
        "investigation_checkpoints",
        sa.Column("checkpoint_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "version", name="uq_checkpoints_version"),
    )
    op.create_index("ix_investigation_checkpoints_run_id", "investigation_checkpoints", ["run_id"])
    op.create_table(
        "scenarios",
        sa.Column("scenario_id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("team_id", sa.String(128), nullable=False),
        sa.Column("snapshot_id", sa.String(128), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("run_id", "kind", name="uq_scenarios_kind"),
        sa.CheckConstraint("kind IN ('hire', 'reallocate', 'do_nothing')", name="ck_scenarios_kind"),
    )
    op.create_index("ix_scenarios_run_id", "scenarios", ["run_id"])
    op.create_index("ix_scenarios_tenant_id", "scenarios", ["tenant_id"])
    op.create_table(
        "simulation_results",
        sa.Column("simulation_id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("scenario_id", name="uq_simulation_scenario"),
    )
    op.create_table(
        "critic_reviews",
        sa.Column("review_id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("scenario_id", name="uq_critic_scenario"),
    )
    op.create_table(
        "hr_decisions",
        sa.Column("decision_id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("actor_user_id", sa.String(36), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("scenario_hash", sa.String(64), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("scenario_id", name="uq_decision_scenario"),
        sa.CheckConstraint("decision IN ('approve', 'defer', 'reject')", name="ck_decisions_decision"),
    )
    op.create_index("ix_hr_decisions_tenant_id", "hr_decisions", ["tenant_id"])
    op.create_table(
        "requisition_drafts",
        sa.Column("draft_id", sa.String(36), primary_key=True),
        sa.Column("decision_id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("executed", sa.Integer(), nullable=False),
        sa.UniqueConstraint("decision_id", name="uq_draft_decision"),
        sa.CheckConstraint("executed = 0", name="ck_drafts_not_executed"),
    )
    op.create_table(
        "jira_checkpoints",
        sa.Column("tenant_id", sa.String(128), primary_key=True),
        sa.Column("issue_id", sa.String(64), primary_key=True),
        sa.Column("snapshot_id", sa.String(128), nullable=False),
    )


def downgrade():
    for name in (
        "jira_checkpoints", "requisition_drafts", "hr_decisions", "critic_reviews", "simulation_results",
        "scenarios", "investigation_checkpoints", "investigation_answers", "investigation_runs",
        "forecast_results", "metric_results", "data_imports",
    ):
        op.drop_table(name)
