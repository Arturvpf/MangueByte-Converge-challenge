"""Record aggregate outcomes for a versioned human decision."""
from datetime import date, datetime, timezone

from pydantic import Field, field_validator
from sqlalchemy import select

from backend.app.auth.permissions import Permission
from backend.app.contracts.v1 import Contract, nonempty
from backend.app.decisions.service import _audit, _scenario
from backend.app.flow.errors import FlowError
from backend.app.flow.models import DecisionObservation, DecisionRow


class ObservationIn(Contract):
    week_start: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    arrival_cases: int = Field(ge=0, le=1_000_000)
    backlog_end: int = Field(ge=0, le=1_000_000)
    sla_fraction: float | None = Field(default=None, ge=0, le=1)
    incremental_cost_brl: float | None = Field(default=None, ge=0, le=1_000_000_000)
    adverse_effect: bool = False
    disputed: bool = False
    justification: str = Field(min_length=1, max_length=1000)

    _text = field_validator("justification")(nonempty)

    @field_validator("week_start")
    @classmethod
    def valid_date(cls, value):
        return date.fromisoformat(value).isoformat()


def _decision(session, principal, scenario_id):
    scenario = _scenario(session, principal, scenario_id)
    decision = session.scalar(select(DecisionRow).where(
        DecisionRow.scenario_id == scenario_id, DecisionRow.tenant_id == scenario.tenant_id,
    ))
    if decision is None or decision.scenario_hash != scenario.content_hash:
        raise FlowError(409, "DECISION_REQUIRED")
    return scenario, decision


def record_observation(session, principal, scenario_id, observation):
    scenario, decision = _decision(session, principal, scenario_id)
    if not principal.can(Permission.DECISION_WRITE, scenario.team_id):
        raise FlowError(403, "FORBIDDEN_SCOPE", scenario.team_id)
    if decision.decision != "approve" and (scenario.kind != "do_nothing" or decision.decision != "defer"):
        raise FlowError(409, "INTERVENTION_NOT_APPROVED")
    projection = scenario.payload.get("quantitative") or {}
    week = next((w for w in projection.get("weeks", []) if w["starts"] == observation.week_start), None)
    if week is None:
        raise FlowError(422, "WEEK_OUTSIDE_PLAN")
    data = observation.model_dump(mode="json")
    existing = session.get(DecisionObservation, (decision.decision_id, observation.week_start))
    if existing:
        if existing.payload["observed"] != data:
            raise FlowError(409, "OBSERVATION_ALREADY_RECORDED")
        return existing.payload
    queue = next((row for row in projection.get("queue", {}).get("weeks", [])
                  if row["starts"] == observation.week_start), {})
    planned = {"arrival_cases": week.get("arrival_cases"), "backlog_end": week.get("backlog_cases"),
               "sla_fraction": (queue.get("sla_fraction") or {}).get("mean"),
               "incremental_cost_brl": week.get("incremental_cost_brl")}
    delta = {key: None if value is None or data[key] is None else data[key] - value
             for key, value in planned.items()}
    forecast_error = delta["arrival_cases"]
    prior_backlog = week.get("backlog_cases")
    payload = {
        "decision_id": decision.decision_id, "scenario_hash": scenario.content_hash,
        "synthetic_plan": projection.get("synthetic"), "observed": data, "planned": planned, "delta": delta,
        "recommend_investigation": bool(
            data["adverse_effect"] or data["disputed"] or (prior_backlog is not None and delta["backlog_end"] > 5)
            or (forecast_error is not None and abs(forecast_error) > max(5, 0.15 * planned["arrival_cases"]))
            or (delta["sla_fraction"] is not None and delta["sla_fraction"] < -0.05)
            or (delta["incremental_cost_brl"] is not None and delta["incremental_cost_brl"] > 0)
        ),
    }
    session.add(DecisionObservation(decision_id=decision.decision_id, week_start=observation.week_start,
                                    actor_user_id=principal.user_id, payload=payload,
                                    created_at=datetime.now(timezone.utc)))
    _audit(session, principal, "decision.observe", decision.decision_id, scenario.team_id,
           scenario_id=scenario_id, week_start=observation.week_start)
    session.flush()
    return payload


def list_observations(session, principal, scenario_id):
    _, decision = _decision(session, principal, scenario_id)
    rows = session.scalars(select(DecisionObservation).where(
        DecisionObservation.decision_id == decision.decision_id,
    ).order_by(DecisionObservation.week_start))
    return {"items": [row.payload for row in rows]}
