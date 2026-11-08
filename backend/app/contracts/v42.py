"""PRD v4.2 contracts. Explicitly distinct from persisted v1 snapshots.

These types describe *aggregate* operational events; no employee identifiers,
clinical fields, protected traits, or free-form ticket bodies are accepted.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class V42Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class DemandFlow(V42Contract):
    """Backlog ledger and latent unmet demand are different quantities.

    `unmet_cases` means demand *not registered* as incoming, to avoid double
    counting tickets already present in the queue. Reopened items return to the
    backlog but are not treated as newly arrived customers.
    """
    team_id: str = Field(min_length=1)
    skill_id: str = Field(min_length=1)
    period_start: date
    period_end_exclusive: date
    unit: Literal["cases_per_period"]
    incoming_cases: int = Field(ge=0)
    completed_cases: int = Field(ge=0)
    cancelled_cases: int = Field(ge=0)
    reopened_cases: int = Field(ge=0)
    unmet_cases: int = Field(ge=0)
    backlog_start: int = Field(ge=0)
    backlog_end: int = Field(ge=0)
    source_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def reconcile(self):
        if self.period_end_exclusive <= self.period_start:
            raise ValueError("period must have positive duration")
        expected = (self.backlog_start + self.incoming_cases + self.reopened_cases
                    - self.completed_cases - self.cancelled_cases)
        if self.backlog_end != expected:
            raise ValueError("BACKLOG_MISMATCH")
        return self

    @property
    def demand_exposure(self) -> int:
        """Registered arrivals plus demand demonstrably outside that register."""
        return self.incoming_cases + self.unmet_cases


class ManagerReport(V42Contract):
    """A manager's description is a report, not a verified observation."""
    author_user_id: str = Field(min_length=1)
    reported_at: datetime
    statement: str = Field(min_length=1, max_length=2000)
    verification: Literal["unverified"] = "unverified"

    @model_validator(mode="after")
    def require_tz(self):
        if self.reported_at.tzinfo is None or self.reported_at.utcoffset() is None:
            raise ValueError("reported_at must be timezone-aware")
        return self


class CoverageNeed(V42Contract):
    skill_id: str = Field(min_length=1)
    shift_id: str = Field(min_length=1)
    interval_start: datetime
    interval_end: datetime
    mandatory_hours: int = Field(ge=0)
    target_hours: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_interval(self):
        if (self.interval_start.tzinfo is None or self.interval_end.tzinfo is None
                or self.interval_start.utcoffset() is None or self.interval_end.utcoffset() is None):
            raise ValueError("coverage interval needs timezone-aware boundaries")
        if self.interval_end <= self.interval_start:
            raise ValueError("coverage interval must have positive duration")
        if self.mandatory_hours > self.target_hours:
            raise ValueError("mandatory coverage cannot exceed target")
        return self


class ReadyCapacity(V42Contract):
    pool_id: str = Field(min_length=1)
    skill_id: str = Field(min_length=1)
    shift_id: str = Field(min_length=1)
    available_hours: int = Field(ge=0)
    ready_at: datetime
    qualification_verified: bool
    approved_work_schedule: bool

    @model_validator(mode="after")
    def ready_is_aware(self):
        if self.ready_at.tzinfo is None or self.ready_at.utcoffset() is None:
            raise ValueError("ready_at must be timezone-aware")
        return self


class Assignment(V42Contract):
    pool_id: str = Field(min_length=1)
    skill_id: str = Field(min_length=1)
    shift_id: str = Field(min_length=1)
    hours: int = Field(ge=0)


class ScenarioReadiness(V42Contract):
    """Hard-rule verification is an *input from the policy validator*, not an LLM claim."""
    policy_evidence_id: str | None = None
    policy_rules_current: bool = False
    rest_and_daily_limits_verified: bool = False
    budget_approved: bool = False
    legal_modality_verified: bool = False


class PlanVerification(V42Contract):
    scenario_id: str = Field(min_length=1)
    status: Literal["valid", "blocked"]
    mandatory_coverage_met: bool
    operational_residual_hours: int = Field(ge=0)
    violations: list[str]
    limitations: list[str]


class HiringLeadTime(V42Contract):
    requested_at: date
    recruitment_days: int = Field(ge=0)
    admission_days: int = Field(ge=0)
    training_days: int = Field(ge=0)
    mentor_hours: int = Field(ge=0)
    ramp_up_fraction: Decimal = Field(ge=0, le=1)

    @property
    def first_eligible_day(self) -> date:
        return self.requested_at + timedelta(
            days=self.recruitment_days + self.admission_days + self.training_days
        )


class PostActionReview(V42Contract):
    """Restricted post-decision comparison, no employee-level evaluation."""
    scenario_id: str = Field(min_length=1)
    observed_metrics: dict[str, float]
    forecast_errors: dict[str, float | None]
    unintended_effects: list[str]
    contestations: list[str]
    next_step: str = Field(min_length=1)
    reviewer_user_id: str = Field(min_length=1)
