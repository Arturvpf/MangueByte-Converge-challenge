"""Tables are isolated until the shared migration order is agreed."""
from sqlalchemy import JSON, DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class JobsBase(DeclarativeBase):
    pass


class Run(JobsBase):
    __tablename__ = "job_runs"
    __table_args__ = (UniqueConstraint("tenant_id", "team_id", "idempotency_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(200), nullable=False)
    team_id: Mapped[str] = mapped_column(String(200), nullable=False)
    snapshot_id: Mapped[str] = mapped_column(String(200), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(200), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    steps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_steps: Mapped[int] = mapped_column(Integer, nullable=False)
    cost: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    max_cost: Mapped[float] = mapped_column(Float, nullable=False)
    deadline: Mapped[object] = mapped_column(DateTime, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    lease_token: Mapped[str | None] = mapped_column(String(36))
    lease_until: Mapped[object | None] = mapped_column(DateTime)
    question_id: Mapped[str | None] = mapped_column(String(36))
    failure: Mapped[str | None] = mapped_column(String(80))


class Checkpoint(JobsBase):
    __tablename__ = "job_checkpoints"
    __table_args__ = (UniqueConstraint("run_id", "version"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime, nullable=False)


class Answer(JobsBase):
    __tablename__ = "job_answers"
    __table_args__ = (UniqueConstraint("run_id", "idempotency_key"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
