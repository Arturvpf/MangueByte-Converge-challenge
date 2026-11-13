"""Investigation, scenarios and decisions."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.app.audit.log import as_utc, record_event
from backend.app.audit.models import AuditEvent
from backend.app.auth.dependencies import deny, require_permission
from backend.app.auth.permissions import Permission, Principal
from backend.app.contracts.v1 import Contract, nonempty
from pydantic import field_validator
from backend.app.decisions.monitor import ObservationIn, list_observations, record_observation
from backend.app.decisions.service import decide, draft
from backend.app.flow.errors import FlowError
from backend.app.flow.models import CriticRow, DecisionRow, InvestigationRun, RequisitionDraftRow, ScenarioRow
from backend.app.planning.premises import PlanningPremises
from backend.app.workflow.replanning import list_evidence, replan
from backend.app.workflow.service import advance, answer, create_run, _run

router = APIRouter(prefix="/api", tags=["workflow"])


class RunIn(Contract):
    team_id: str = Field(min_length=1, max_length=128)
    snapshot_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=1, max_length=128)
    cycle_limit: int = Field(ge=1, le=20)

    _text = field_validator("team_id", "snapshot_id", "idempotency_key")(nonempty)


class AnswerIn(Contract):
    question_id: str = Field(min_length=1, max_length=64)
    answer: str = Field(min_length=1, max_length=2000)
    idempotency_key: str = Field(min_length=1, max_length=128)

    _text = field_validator("question_id", "answer", "idempotency_key")(nonempty)


class DecisionIn(Contract):
    decision: Literal["approve", "defer", "reject"]
    reason: str = Field(min_length=1, max_length=1000)
    expected_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=1, max_length=128)

    _text = field_validator("reason", "expected_hash", "idempotency_key")(nonempty)


class DraftIn(Contract):
    idempotency_key: str = Field(min_length=1, max_length=128)

    _text = field_validator("idempotency_key")(nonempty)


def _call(request, principal, permission, fn):
    try:
        with request.app.state.session_factory() as session:
            result = fn(session)
            session.commit()
            return result
    except IntegrityError:
        raise HTTPException(status_code=409, detail={"code": "CONCURRENT_CHANGE"}) from None
    except FlowError as exc:
        if exc.status == 403:
            deny(request, principal, permission, exc.team_id)
        raise HTTPException(status_code=exc.status, detail={"code": exc.code, "message": exc.code}) from None


def _public_run(run) -> dict:
    return {
        "run_id": run.run_id, "team_id": run.team_id, "snapshot_id": run.snapshot_id, "state": run.state,
        "version": run.version, "cycle_count": run.cycle_count, "cycle_limit": run.cycle_limit,
        "failure": run.failure, "report": run.report, "forecast": run.forecast, "trace_id": run.trace_id,
    }


@router.post("/investigations", status_code=202)
def open_run(body: RunIn, request: Request, principal: Principal = Depends(require_permission(Permission.INVESTIGATION_RUN))):
    return _call(request, principal, Permission.INVESTIGATION_RUN, lambda session: _public_run(create_run(
        session, principal, team_id=body.team_id, snapshot_id=body.snapshot_id, idempotency_key=body.idempotency_key,
        cycle_limit=body.cycle_limit,
    )))


@router.get("/investigations")
def list_runs(request: Request, principal: Principal = Depends(require_permission(Permission.SCENARIO_READ))):
    """Resumption index: only runs in the authenticated tenant and accessible teams."""
    def run(session):
        query = select(InvestigationRun).where(InvestigationRun.tenant_id == principal.tenant_id)
        if not principal.tenant_wide(Permission.SCENARIO_READ):
            allowed = list(principal.team_ids(Permission.SCENARIO_READ))
            if not allowed:
                return {"items": []}
            query = query.where(InvestigationRun.team_id.in_(allowed))
        rows = session.scalars(query.order_by(InvestigationRun.updated_at.desc()).limit(100))
        return {"items": [
            {"run_id": row.run_id, "team_id": row.team_id, "snapshot_id": row.snapshot_id,
             "state": row.state, "updated_at": row.updated_at.isoformat()}
            for row in rows if principal.can(Permission.SCENARIO_READ, row.team_id)
        ]}
    return _call(request, principal, Permission.SCENARIO_READ, run)


@router.get("/investigations/{run_id}")
def read_run(run_id: str, request: Request, principal: Principal = Depends(require_permission(Permission.SCENARIO_READ))):
    return _call(request, principal, Permission.SCENARIO_READ, lambda session: _public_run(_run(session, principal, run_id)))


@router.get("/investigations/{run_id}/audit")
def read_run_audit(run_id: str, request: Request, principal: Principal = Depends(require_permission(Permission.SCENARIO_READ))):
    def run(session):
        item = _run(session, principal, run_id)
        if not principal.can(Permission.AUDIT_READ, item.team_id):
            raise FlowError(403, "FORBIDDEN_SCOPE", item.team_id)
        scenario_ids = set(session.scalars(select(ScenarioRow.scenario_id).where(ScenarioRow.run_id == item.run_id)))
        decision_ids = set(session.scalars(select(DecisionRow.decision_id).where(DecisionRow.scenario_id.in_(scenario_ids)))) if scenario_ids else set()
        draft_ids = set(session.scalars(select(RequisitionDraftRow.draft_id).where(RequisitionDraftRow.decision_id.in_(decision_ids)))) if decision_ids else set()
        watched = {item.run_id, *scenario_ids, *decision_ids, *draft_ids}
        events = session.scalars(select(AuditEvent).where(
            AuditEvent.tenant_id == principal.tenant_id, AuditEvent.team_id == item.team_id,
        ).order_by(AuditEvent.occurred_at))
        items = []
        for event in events:
            details = event.details or {}
            if event.resource_id not in watched and details.get("scenario_id") not in scenario_ids:
                continue
            items.append({
                "id": event.id, "occurred_at": as_utc(event.occurred_at).isoformat(), "trace_id": event.trace_id,
                "action": event.action, "outcome": event.outcome, "resource_type": event.resource_type,
                "resource_id": event.resource_id, "details": details,
            })
        record_event(
            session, action="audit.read", outcome="success", tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id, team_id=item.team_id, resource_type="investigation",
            resource_id=item.run_id, details={"result_count": len(items)},
        )
        return {"items": items[-100:]}
    return _call(request, principal, Permission.AUDIT_READ, run)


@router.post("/investigations/{run_id}/advance")
def advance_run(run_id: str, request: Request, principal: Principal = Depends(require_permission(Permission.INVESTIGATION_RUN))):
    return _call(request, principal, Permission.INVESTIGATION_RUN, lambda session: _public_run(advance(session, principal, run_id)))


@router.post("/investigations/{run_id}/answers")
def answer_run(run_id: str, body: AnswerIn, request: Request,
               principal: Principal = Depends(require_permission(Permission.INVESTIGATION_ANSWER))):
    return _call(request, principal, Permission.INVESTIGATION_ANSWER, lambda session: _public_run(answer(
        session, principal, run_id, question_id=body.question_id, text=body.answer, idempotency_key=body.idempotency_key,
    )))


@router.get("/investigations/{run_id}/forecast")
def read_forecast(run_id: str, request: Request, principal: Principal = Depends(require_permission(Permission.DATA_READ))):
    def run(session):
        item = _run(session, principal, run_id)
        if not principal.can(Permission.DATA_READ, item.team_id):
            raise FlowError(403, "FORBIDDEN_SCOPE", item.team_id)
        return item.forecast
    return _call(request, principal, Permission.DATA_READ, run)


@router.get("/investigations/{run_id}/scenarios")
def list_scenarios(run_id: str, request: Request, principal: Principal = Depends(require_permission(Permission.SCENARIO_READ))):
    def run(session):
        item = _run(session, principal, run_id)
        rows = session.scalars(select(ScenarioRow).where(
            ScenarioRow.run_id == item.run_id, ScenarioRow.version == item.cycle_count + 1,
        ).order_by(ScenarioRow.kind))
        return {"items": [row.payload for row in rows]}
    return _call(request, principal, Permission.SCENARIO_READ, run)


@router.get("/scenarios/{scenario_id}")
def read_scenario(scenario_id: str, request: Request, principal: Principal = Depends(require_permission(Permission.SCENARIO_READ))):
    def run(session):
        row = session.get(ScenarioRow, scenario_id)
        if row is None or row.tenant_id != principal.tenant_id or not principal.can(Permission.SCENARIO_READ, row.team_id):
            raise FlowError(404, "NOT_FOUND")
        review = session.scalar(select(CriticRow).where(CriticRow.scenario_id == scenario_id))
        decision = session.scalar(select(DecisionRow).where(DecisionRow.scenario_id == scenario_id))
        return {
            "scenario": row.payload,
            "critic": None if review is None else review.payload,
            "decision": None if decision is None else {"decision_id": decision.decision_id, "decision": decision.decision, "scenario_hash": decision.scenario_hash},
        }
    return _call(request, principal, Permission.SCENARIO_READ, run)


@router.post("/scenarios/{scenario_id}/decisions")
def decide_scenario(scenario_id: str, body: DecisionIn, request: Request,
                    principal: Principal = Depends(require_permission(Permission.DECISION_WRITE))):
    def run(session):
        stored = decide(
            session, principal, scenario_id, decision=body.decision, reason=body.reason,
            expected_hash=body.expected_hash, idempotency_key=body.idempotency_key,
        )
        return {"decision_id": stored.decision_id, "decision": stored.decision, "scenario_hash": stored.scenario_hash, "executed": False}
    return _call(request, principal, Permission.DECISION_WRITE, run)


@router.post("/scenarios/{scenario_id}/requisition-drafts")
def draft_scenario(scenario_id: str, body: DraftIn, request: Request,
                   principal: Principal = Depends(require_permission(Permission.REQUISITION_DRAFT))):
    def run(session):
        stored = draft(session, principal, scenario_id, idempotency_key=body.idempotency_key)
        if stored.executed != 0:
            raise FlowError(409, "NOT_CONCLUSIVE")
        return stored.payload
    return _call(request, principal, Permission.REQUISITION_DRAFT, run)


class ReplanIn(Contract):
    snapshot_id: str = Field(min_length=1, max_length=128)
    expected_version: int = Field(ge=0)
    idempotency_key: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=1000)

    premises: PlanningPremises | None = None

    _text = field_validator("snapshot_id", "idempotency_key", "reason")(nonempty)


@router.post("/investigations/{run_id}/replan")
def replan_run(run_id: str, body: ReplanIn, request: Request,
               principal: Principal = Depends(require_permission(Permission.DECISION_WRITE))):
    return _call(request, principal, Permission.DECISION_WRITE, lambda session: _public_run(
        replan(session, principal, run_id, **body.model_dump(exclude={"premises"}), premises=body.premises),
    ))


@router.get("/investigations/{run_id}/evidence")
def read_evidence(run_id: str, request: Request,
                  principal: Principal = Depends(require_permission(Permission.DECISION_WRITE))):
    return _call(request, principal, Permission.DECISION_WRITE,
                 lambda session: list_evidence(session, principal, run_id))


@router.post("/scenarios/{scenario_id}/observations")
def record_outcome(scenario_id: str, body: ObservationIn, request: Request,
                   principal: Principal = Depends(require_permission(Permission.DECISION_WRITE))):
    return _call(request, principal, Permission.DECISION_WRITE,
                 lambda session: record_observation(session, principal, scenario_id, body))


@router.get("/scenarios/{scenario_id}/observations")
def read_outcomes(scenario_id: str, request: Request,
                  principal: Principal = Depends(require_permission(Permission.DECISION_WRITE))):
    return _call(request, principal, Permission.DECISION_WRITE,
                 lambda session: list_observations(session, principal, scenario_id))


@router.get("/investigations/{run_id}/planning-summary")
def planning_summary(run_id: str, request: Request,
                     principal: Principal = Depends(require_permission(Permission.DATA_READ))):
    # Model-facing boundary: allowlisted team totals and controlled labels only.
    # Exclude source names, manager text, staff/pool identifiers and evidence notes.
    def summarize(session):
        item = _run(session, principal, run_id)
        if not (principal.can(Permission.DATA_READ, item.team_id)
                and principal.can(Permission.SCENARIO_READ, item.team_id)):
            raise FlowError(404, "NOT_FOUND")
        forecast = item.forecast
        if forecast is None:
            raise FlowError(409, "PLANNING_NOT_READY")
        # Suppress low-volume operational series at the model boundary.
        if forecast.get("source_kind") != "synthetic" and (
            not forecast["points"] or any(
                point["point_estimate"] is None or point["point_estimate"] < 10 for point in forecast["points"]
            )
        ):
            raise FlowError(409, "AGGREGATION_REQUIRED")
        rows = session.scalars(select(ScenarioRow).where(
            ScenarioRow.run_id == item.run_id, ScenarioRow.tenant_id == item.tenant_id,
            ScenarioRow.team_id == item.team_id, ScenarioRow.version == item.cycle_count + 1,
        ).order_by(ScenarioRow.kind))
        scenarios = []
        for row in rows:
            q = row.payload.get("quantitative")
            if not q:
                continue
            cost = q.get("cost_range_brl") or {}
            weeks = q.get("weeks") or []
            scenarios.append({
                "kind": row.kind, "version": row.version, "solver_status": q["solver_status"],
                "residual_hours": q.get("residual_hours"),
                "hours_saved_vs_baseline": q.get("hours_saved_vs_baseline"),
                "implementation_days": q.get("implementation_days"),
                "cost_min_brl": cost.get("min"), "cost_max_brl": cost.get("max"),
                "cost_status": q.get("cost_status", "unavailable"),
                "backlog_end": weeks[-1].get("backlog_cases") if weeks else None,
                "sla_fraction": ((q.get("queue") or {}).get("sla_fraction") or {}).get("mean"),
                "approval_ready": False,
            })
        return {"source_kind": forecast.get("source_kind"), "forecast_status": forecast["status"],
                "usable_for_planning": forecast.get("usable_for_planning", forecast["status"] != "abstained"),
                "points": [{"starts": p["period"]["start"], "estimate": p["point_estimate"],
                            **{key: p.get(key) for key in ("p10", "p50", "p90")}}
                           for p in forecast["points"]],
                "scenarios": scenarios}
    return _call(request, principal, Permission.DATA_READ, summarize)
