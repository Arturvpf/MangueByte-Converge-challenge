"""Scenario, simulation, critic and decision contracts. They are not in contracts/v1.py."""
from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from backend.app.contracts.v1 import Contract, aware, nonempty


class AllocationOut(Contract):
    pool_id: str = Field(min_length=1)
    skill_id: str = Field(min_length=1)
    shift_id: str = Field(min_length=1)
    hours: int = Field(ge=0)

    _ids = field_validator("pool_id", "skill_id", "shift_id")(nonempty)


class ScenarioCandidate(Contract):
    schema_version: Literal["1.0"]
    scenario_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    team_id: str = Field(min_length=1)
    data_snapshot_id: str = Field(min_length=1)
    kind: Literal["hire", "temporary", "reallocate", "redesign", "do_nothing"]
    version: int = Field(ge=1)
    actions: list[str]
    assumptions: list[str]
    dependencies: list[str]
    gaps: list[str]
    preliminary_cost: str | None
    headcount_delta: int | None
    residual_hours: int | None
    conclusive: bool
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    rule_versions: list[str]
    role_mix: list[dict] = Field(default_factory=list)
    lead_time_and_ramp_up: dict | None = None
    legal_flags: list[str] = Field(default_factory=list)
    costs_estimated: bool = False

    _ids = field_validator("scenario_id", "tenant_id", "team_id", "data_snapshot_id", "content_hash")(nonempty)


class SimulationResult(Contract):
    schema_version: Literal["1.0"]
    simulation_id: str = Field(min_length=1)
    scenario_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    team_id: str = Field(min_length=1)
    data_snapshot_id: str = Field(min_length=1)
    status: Literal["optimal", "feasible", "infeasible", "unknown"]
    allocations: list[AllocationOut]
    residual_hours: dict[str, int]
    limitations: list[str]
    assumptions: list[str]

    _ids = field_validator("simulation_id", "scenario_id", "tenant_id", "team_id", "data_snapshot_id")(nonempty)


class CriticResult(Contract):
    schema_version: Literal["1.0"]
    review_id: str = Field(min_length=1)
    scenario_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    team_id: str = Field(min_length=1)
    verdict: Literal["noted", "blocked", "needs_data"]
    risks: list[str]
    blocks: list[str]
    missing_data: list[str]
    hard_constraint_failed: bool
    revision_requested: bool

    _ids = field_validator("review_id", "scenario_id", "tenant_id", "team_id")(nonempty)


class DecisionRecord(Contract):
    schema_version: Literal["1.0"]
    decision_id: str = Field(min_length=1)
    scenario_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    team_id: str = Field(min_length=1)
    data_snapshot_id: str = Field(min_length=1)
    scenario_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    rule_versions: list[str]
    decision: Literal["approve", "defer", "reject"]
    reason: str = Field(min_length=1, max_length=1000)
    actor_user_id: str = Field(min_length=1, max_length=36)
    decided_at: datetime
    executed: Literal[False]

    _ids = field_validator("decision_id", "scenario_id", "tenant_id", "team_id", "data_snapshot_id", "reason", "actor_user_id")(nonempty)
    _time = field_validator("decided_at")(aware)


class RequisitionDraft(Contract):
    schema_version: Literal["1.0"]
    draft_id: str = Field(min_length=1)
    decision_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    team_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    limitations: list[str]
    executed: Literal[False]

    _ids = field_validator("draft_id", "decision_id", "tenant_id", "team_id", "summary")(nonempty)
