from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Generic, Literal, TypeVar
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing_extensions import Self


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, strict=True, protected_namespaces=())


Id = str  # Opaque, nonempty identifiers; authorization never derives from these fields.


def nonempty(value: str) -> str:
    if not value.strip() or value != value.strip():
        raise ValueError('identifier/text must be nonempty and have no outer whitespace')
    return value


class Versioned(Contract):
    schema_version: Literal['1.0']


class Scope(Versioned):
    tenant_id: Id = Field(min_length=1)
    team_id: Id = Field(min_length=1)

    _ids = field_validator('tenant_id', 'team_id')(nonempty)


class Period(Contract):
    start: date
    end_exclusive: date
    timezone: str

    @field_validator('timezone')
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError('timezone must be a valid IANA zone')
        return value

    @model_validator(mode='after')
    def ordered(self) -> Self:
        if self.end_exclusive <= self.start:
            raise ValueError('end_exclusive must follow start')
        return self


def aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('timestamp requires an explicit UTC offset')
    return value


class ToolRequest(Scope):
    run_id: Id = Field(min_length=1)
    data_snapshot_id: Id = Field(min_length=1)
    policy_version_ids: list[Id]
    requested_at: datetime
    idempotency_key: Id = Field(min_length=1)

    _ids = field_validator('run_id', 'data_snapshot_id', 'idempotency_key')(nonempty)
    _time = field_validator('requested_at')(aware)

    @field_validator('policy_version_ids')
    @classmethod
    def policies(cls, values: list[str]) -> list[str]:
        for value in values:
            nonempty(value)
        if len(values) != len(set(values)):
            raise ValueError('policy versions must be unique')
        return values


class EvidenceRef(Contract):
    evidence_id: Id = Field(min_length=1)
    tenant_id: Id = Field(min_length=1)
    team_id: Id = Field(min_length=1)
    data_snapshot_id: Id = Field(min_length=1)
    description: str = Field(min_length=1)

    _text = field_validator('evidence_id', 'tenant_id', 'team_id', 'data_snapshot_id', 'description')(nonempty)


class ErrorCode(str, Enum):
    INSUFFICIENT_DATA = 'INSUFFICIENT_DATA'
    UNIT_MISMATCH = 'UNIT_MISMATCH'
    POLICY_REVIEW_REQUIRED = 'POLICY_REVIEW_REQUIRED'
    FORBIDDEN_SCOPE = 'FORBIDDEN_SCOPE'
    SOLVER_TIMEOUT = 'SOLVER_TIMEOUT'
    INFEASIBLE = 'INFEASIBLE'
    INTEGRATION_UNAVAILABLE = 'INTEGRATION_UNAVAILABLE'


class ContractError(Contract):
    code: ErrorCode
    message: str = Field(min_length=1)
    retryable: bool
    details: list[str]

    _message = field_validator('message')(nonempty)


T = TypeVar('T')


class ToolResponse(Scope, Generic[T]):
    status: Literal['ok', 'error']
    result: T | None
    error: ContractError | None
    evidence_refs: list[EvidenceRef]
    data_version: Id = Field(min_length=1)
    model_version: str | None
    rule_versions: list[Id]
    generated_at: datetime
    limitations: list[str]
    trace_id: Id = Field(min_length=1)

    _ids = field_validator('data_version', 'trace_id')(nonempty)
    _time = field_validator('generated_at')(aware)

    @model_validator(mode='after')
    def consistent(self) -> Self:
        if self.status == 'ok' and (not self.__class__.__pydantic_generic_metadata__['args'] or not isinstance(self.result, Scope)):
            raise ValueError('successful responses require a typed, scoped result')
        for version in self.rule_versions:
            nonempty(version)
        if len(self.rule_versions) != len(set(self.rule_versions)):
            raise ValueError('rule versions must be unique')
        if (self.status == 'ok' and (self.result is None or self.error is not None)) or (self.status == 'error' and (self.error is None or self.result is not None)):
            raise ValueError('ok requires result only; error requires error only')
        for ref in self.evidence_refs:
            if (ref.tenant_id, ref.team_id, ref.data_snapshot_id) != (self.tenant_id, self.team_id, self.data_version):
                raise ValueError('evidence must match response scope and data version')
        if isinstance(self.result, Scope) and (self.result.tenant_id, self.result.team_id) != (self.tenant_id, self.team_id):
            raise ValueError('result must match response scope')
        if self.result is not None and hasattr(self.result, 'data_snapshot_id') and self.result.data_snapshot_id != self.data_version:
            raise ValueError('result must match data version')
        if self.result is not None and hasattr(self.result, 'model_version') and self.result.model_version != self.model_version:
            raise ValueError('result model version must match response')
        return self


class CapacityPool(Contract):
    pool_id: Id = Field(min_length=1)
    available_hours: float | None = Field(ge=0)

    _id = field_validator('pool_id')(nonempty)


class CapacityRow(Contract):
    skill_id: Id = Field(min_length=1)
    shift_id: Id = Field(min_length=1)
    eligible_hours: float | None = Field(ge=0)
    pool_ids: list[Id] = Field(min_length=1)
    availability_fraction: float | None = Field(ge=0, le=1)
    # Cost bands are aggregate hourly estimates, not individual salaries.
    cost_min: float | None = Field(ge=0)
    cost_max: float | None = Field(ge=0)
    currency: Literal['BRL'] | None

    _ids = field_validator('skill_id', 'shift_id')(nonempty)

    @model_validator(mode='after')
    def costs(self) -> Self:
        if (self.cost_min is None) != (self.cost_max is None):
            raise ValueError('cost bounds must both be known or both null')
        if (self.cost_min is None) != (self.currency is None):
            raise ValueError('known cost bounds require currency; unknown bounds require null currency')
        if self.cost_min is not None and self.cost_max < self.cost_min:
            raise ValueError('cost range is reversed')
        return self


class SkillCapacitySnapshot(Scope):
    data_snapshot_id: Id = Field(min_length=1)
    period: Period
    hours_unit: Literal['hours_per_period']
    pools: list[CapacityPool] = Field(min_length=1)
    rows: list[CapacityRow] = Field(min_length=1)
    limitations: list[str]

    _id = field_validator('data_snapshot_id')(nonempty)

    @model_validator(mode='after')
    def unique_rows(self) -> Self:
        pool_ids = [p.pool_id for p in self.pools]
        if len(pool_ids) != len(set(pool_ids)):
            raise ValueError('duplicate capacity pool')
        for row in self.rows:
            if len(row.pool_ids) != len(set(row.pool_ids)) or not set(row.pool_ids).issubset(pool_ids):
                raise ValueError('row pool IDs must be unique and exist')
            pools = [p for p in self.pools if p.pool_id in row.pool_ids]
            if row.eligible_hours is not None and all(p.available_hours is not None for p in pools) and row.eligible_hours > sum(p.available_hours for p in pools):
                raise ValueError('eligible hours exceed referenced pool budgets')
        keys = [(r.skill_id, r.shift_id) for r in self.rows]
        if len(keys) != len(set(keys)):
            raise ValueError('duplicate skill/shift row')
        return self


class DemandRecord(Contract):
    skill_id: Id = Field(min_length=1)
    period: Period
    quantity: float | None = Field(ge=0)
    unit: Literal['cases_per_period']

    _id = field_validator('skill_id')(nonempty)


class DemandSnapshot(Scope):
    data_snapshot_id: Id = Field(min_length=1)
    records: list[DemandRecord] = Field(min_length=1)
    limitations: list[str]

    _id = field_validator('data_snapshot_id')(nonempty)


    @model_validator(mode='after')
    def nonoverlapping_records(self) -> Self:
        zones = {r.period.timezone for r in self.records}
        if len(zones) != 1:
            raise ValueError('demand periods must use one timezone')
        for skill_id in {r.skill_id for r in self.records}:
            records = sorted((r for r in self.records if r.skill_id == skill_id), key=lambda r: r.period.start)
            if any(a.period.end_exclusive > b.period.start for a, b in zip(records, records[1:])):
                raise ValueError('demand periods for a skill must not overlap')
        return self


class Hypothesis(Contract):
    hypothesis_id: Id = Field(min_length=1)
    statement: str = Field(min_length=1)
    critical: bool
    verification: Literal['supported', 'unverified']
    evidence_ids: list[Id]
    confidence: float | None = Field(ge=0, le=1)

    _text = field_validator('hypothesis_id', 'statement')(nonempty)

    @model_validator(mode='after')
    def backed(self) -> Self:
        if self.verification == 'supported' and not self.evidence_ids:
            raise ValueError('supported hypothesis requires evidence')
        if self.verification == 'unverified' and (self.evidence_ids or self.confidence is not None):
            raise ValueError('unverified hypothesis cannot assert evidence or confidence')
        return self


class Question(Contract):
    question_id: Id = Field(min_length=1)
    text: str = Field(min_length=1)
    status: Literal['pending', 'answered']
    answer: str | None

    _text = field_validator('question_id', 'text')(nonempty)

    @model_validator(mode='after')
    def answer_matches(self) -> Self:
        if self.status == 'pending' and self.answer is not None:
            raise ValueError('pending question cannot have an answer')
        if self.status == 'answered':
            if self.answer is None:
                raise ValueError('answered question requires an answer')
            nonempty(self.answer)
        return self


class InvestigationReport(Scope):
    data_snapshot_id: Id = Field(min_length=1)
    trigger: str = Field(min_length=1)
    hypotheses: list[Hypothesis]
    missing_data: list[str]
    confidence_label: Literal['low', 'medium', 'high', 'unknown']
    evidence_refs: list[EvidenceRef]
    questions: list[Question]
    limitations: list[str]
    confidence: float | None = Field(ge=0, le=1)

    _id = field_validator('data_snapshot_id', 'trigger')(nonempty)

    @model_validator(mode='after')
    def evidence_matches(self) -> Self:
        hypothesis_ids = [h.hypothesis_id for h in self.hypotheses]
        question_ids = [q.question_id for q in self.questions]
        if len(hypothesis_ids) != len(set(hypothesis_ids)) or len(question_ids) != len(set(question_ids)):
            raise ValueError('duplicate hypothesis or question ID')
        ids = [r.evidence_id for r in self.evidence_refs]
        if len(ids) != len(set(ids)):
            raise ValueError('duplicate evidence ID')
        for ref in self.evidence_refs:
            if (ref.tenant_id, ref.team_id, ref.data_snapshot_id) != (self.tenant_id, self.team_id, self.data_snapshot_id):
                raise ValueError('evidence scope/snapshot mismatch')
        for hypothesis in self.hypotheses:
            if not set(hypothesis.evidence_ids).issubset(ids):
                raise ValueError('hypothesis references missing evidence')
        return self


class ForecastPoint(Contract):
    period: Period
    point_estimate: float | None = Field(ge=0)
    lower: float | None = Field(ge=0)
    upper: float | None = Field(ge=0)
    # Empirical predictive quantiles, NOT the simultaneous confidence band.
    p10: float | None = Field(default=None, ge=0)
    p50: float | None = Field(default=None, ge=0)
    p90: float | None = Field(default=None, ge=0)

    @model_validator(mode='after')
    def bounds(self) -> Self:
        if (self.lower is None) != (self.upper is None):
            raise ValueError('forecast bounds must both be known or null')
        if self.lower is not None and (self.point_estimate is None or not self.lower <= self.point_estimate <= self.upper):
            raise ValueError('forecast estimate must fall within bounds')
        quantiles = (self.p10, self.p50, self.p90)
        if any(item is not None for item in quantiles):
            if any(item is None for item in quantiles) or not self.p10 <= self.p50 <= self.p90:
                raise ValueError('predictive quantiles must be complete and ordered')
        return self


class Backtest(Contract):
    method: str = Field(min_length=1)
    evaluated_through: date
    mae: float | None = Field(ge=0)
    wape: float | None = Field(ge=0)
    limitations: list[str]


class ForecastResult(Scope):
    data_snapshot_id: Id = Field(min_length=1)
    model_version: Id = Field(min_length=1)
    method: str = Field(min_length=1)
    status: Literal['calibrated', 'uncalibrated', 'abstained']
    unit: Literal['cases_per_period']
    history_end_exclusive: date
    horizon: Period
    points: list[ForecastPoint]
    interval_description: str | None
    backtest: Backtest | None
    limitations: list[str]

    _ids = field_validator('data_snapshot_id', 'model_version', 'method')(nonempty)

    @model_validator(mode='after')
    def valid_forecast(self) -> Self:
        if self.history_end_exclusive > self.horizon.start:
            raise ValueError('history must end before the forecast horizon')
        if self.backtest and self.backtest.evaluated_through >= self.history_end_exclusive:
            raise ValueError('backtest must precede forecast horizon')
        if self.status == 'abstained' and self.points:
            raise ValueError('abstained forecast cannot contain points')
        if self.status != 'abstained' and not self.points:
            raise ValueError('forecast requires points')
        if self.status == 'calibrated' and (self.backtest is None or self.backtest.mae is None or any(p.point_estimate is None for p in self.points)):
            raise ValueError('calibrated forecast requires measured MAE and estimates')
        if self.backtest and self.backtest.wape is None and not self.backtest.limitations:
            raise ValueError('missing WAPE requires a limitation')
        for p in self.points:
            if p.period.timezone != self.horizon.timezone or p.period.start < self.horizon.start or p.period.end_exclusive > self.horizon.end_exclusive:
                raise ValueError('point outside horizon or timezone mismatch')
            if p.lower is not None and not self.interval_description:
                raise ValueError('bounds require an interval description')
        ordered = sorted(self.points, key=lambda p: p.period.start)
        if any(a.period.end_exclusive > b.period.start for a, b in zip(ordered, ordered[1:])):
            raise ValueError('forecast periods overlap')
        return self


class OrchestrationState(Scope):
    run_id: Id = Field(min_length=1)
    data_snapshot_id: Id = Field(min_length=1)
    state: Literal['CREATED', 'VALIDATING', 'INVESTIGATING', 'PLANNING', 'SIMULATING', 'REVIEWING', 'AWAITING_HUMAN', 'COMPLETED', 'WAITING_INPUT', 'FAILED', 'BLOCKED']
    cycle_count: int = Field(ge=0)
    cycle_limit: int = Field(gt=0)
    trace_id: Id = Field(min_length=1)

    _ids = field_validator('run_id', 'data_snapshot_id', 'trace_id')(nonempty)

    @model_validator(mode='after')
    def limit(self) -> Self:
        if self.cycle_count > self.cycle_limit:
            raise ValueError('cycle limit exceeded')
        return self

