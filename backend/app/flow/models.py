"""Rows for the pilot flow. The mock job engine keeps its own tables."""
from datetime import datetime
from sqlalchemy import JSON, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from backend.app.core.database import Base


class DataImport(Base):
    __tablename__ = "data_imports"
    __table_args__ = (UniqueConstraint("tenant_id", "team_id", "content_hash", name="uq_imports_hash"),)
    import_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    team_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(200), nullable=False)
    snapshot_id: Mapped[str | None] = mapped_column(String(128))
    errors: Mapped[list] = mapped_column(JSON, nullable=False)
    history: Mapped[list] = mapped_column(JSON, nullable=False)
    aggregates: Mapped[dict] = mapped_column(JSON, nullable=False)
    preview: Mapped[dict] = mapped_column(JSON, nullable=False)
    line_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MetricResult(Base):
    __tablename__ = "metric_results"
    __table_args__ = (UniqueConstraint("tenant_id", "team_id", "snapshot_id", name="uq_metrics_snapshot"),)
    metric_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    team_id: Mapped[str] = mapped_column(String(128), nullable=False)
    snapshot_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ForecastRow(Base):
    __tablename__ = "forecast_results"
    __table_args__ = (UniqueConstraint("tenant_id", "team_id", "snapshot_id", name="uq_forecast_snapshot"),)
    forecast_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    team_id: Mapped[str] = mapped_column(String(128), nullable=False)
    snapshot_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class InvestigationRun(Base):
    __tablename__ = "investigation_runs"
    __table_args__ = (UniqueConstraint("tenant_id", "team_id", "idempotency_key", name="uq_runs_idempotency"),)
    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    team_id: Mapped[str] = mapped_column(String(128), nullable=False)
    snapshot_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    cycle_count: Mapped[int] = mapped_column(Integer, nullable=False)
    cycle_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    trace_id: Mapped[str] = mapped_column(String(32), nullable=False)
    failure: Mapped[str | None] = mapped_column(String(64))
    report: Mapped[dict | None] = mapped_column(JSON)
    forecast: Mapped[dict | None] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class InvestigationAnswer(Base):
    __tablename__ = "investigation_answers"
    __table_args__ = (
        UniqueConstraint("run_id", "question_id", name="uq_answers_question"),
        UniqueConstraint("run_id", "idempotency_key", name="uq_answers_key"),
    )
    answer_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    question_id: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    answer: Mapped[str] = mapped_column(String(2000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class InvestigationCheckpoint(Base):
    __tablename__ = "investigation_checkpoints"
    __table_args__ = (UniqueConstraint("run_id", "version", name="uq_checkpoints_version"),)
    checkpoint_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ScenarioRow(Base):
    __tablename__ = "scenarios"
    __table_args__ = (UniqueConstraint("run_id", "kind", name="uq_scenarios_kind"),)
    scenario_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    team_id: Mapped[str] = mapped_column(String(128), nullable=False)
    snapshot_id: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)


class SimulationRow(Base):
    __tablename__ = "simulation_results"
    __table_args__ = (UniqueConstraint("scenario_id", name="uq_simulation_scenario"),)
    simulation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scenario_id: Mapped[str] = mapped_column(String(36), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)


class CriticRow(Base):
    __tablename__ = "critic_reviews"
    __table_args__ = (UniqueConstraint("scenario_id", name="uq_critic_scenario"),)
    review_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scenario_id: Mapped[str] = mapped_column(String(36), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)


class DecisionRow(Base):
    __tablename__ = "hr_decisions"
    __table_args__ = (UniqueConstraint("scenario_id", name="uq_decision_scenario"),)
    decision_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scenario_id: Mapped[str] = mapped_column(String(36), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    actor_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    scenario_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RequisitionDraftRow(Base):
    __tablename__ = "requisition_drafts"
    __table_args__ = (UniqueConstraint("decision_id", name="uq_draft_decision"),)
    draft_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    decision_id: Mapped[str] = mapped_column(String(36), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    executed: Mapped[int] = mapped_column(Integer, nullable=False)


class JiraCheckpoint(Base):
    """Deduplication is scoped to the exact authorized team and Jira source."""
    __tablename__ = "jira_checkpoints"
    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    team_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    source_key: Mapped[str] = mapped_column(String(200), primary_key=True)
    issue_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(String(128), nullable=False)
