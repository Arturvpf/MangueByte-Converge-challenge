"""Checkpointed investigation. Advance resumes from the stored state."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING
from hashlib import sha256
import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.audit.log import record_event
from backend.app.audit.tracing import current_trace_id
from backend.app.auth.permissions import Permission, Principal
from backend.app.contracts.v1 import ForecastResult, InvestigationReport
from backend.app.core.ids import valid_id
from backend.app.data.repository import DataRepository, DataScope
from backend.app.data.schemas import SnapshotData
from backend.app.flow.errors import FlowError
from backend.app.flow.models import (
    CriticRow, DataImport, ForecastRow, InvestigationAnswer, InvestigationCheckpoint, InvestigationRun, ScenarioRow,
    SimulationRow,
)
from backend.app.forecast.engine import forecast_series
from backend.app.investigation.report import apply_answer, build_report
from backend.app.metrics.engine import prepare_matrix
from backend.app.optimization.solver import Row
from backend.app.planning.critic import critique
from backend.app.planning.planner import build_scenarios
from backend.app.planning.schemas import ScenarioCandidate, SimulationResult
from backend.app.policies.catalog import CATALOG
from backend.app.policies.resolver import resolve

PAUSE = {"WAITING_INPUT", "AWAITING_HUMAN", "COMPLETED", "FAILED", "BLOCKED"}


def _now():
    return datetime.now(timezone.utc)


def _audit(session, principal, action, resource_type, resource_id, team_id, **details):
    record_event(
        session, action=action, outcome="success", tenant_id=principal.tenant_id, actor_user_id=principal.user_id,
        team_id=team_id, resource_type=resource_type, resource_id=resource_id, details=details,
    )


def _run(session: Session, principal: Principal, run_id: str) -> InvestigationRun:
    if not principal.has(Permission.INVESTIGATION_RUN) and not principal.has(Permission.SCENARIO_READ):
        raise FlowError(403, "FORBIDDEN_SCOPE")
    run = session.get(InvestigationRun, run_id)
    if run is None or run.tenant_id != principal.tenant_id:
        raise FlowError(404, "NOT_FOUND")
    if not principal.can(Permission.INVESTIGATION_RUN, run.team_id) and not principal.can(Permission.SCENARIO_READ, run.team_id):
        raise FlowError(404, "NOT_FOUND")
    return run


def _snapshot(session, principal, team_id, snapshot_id) -> SnapshotData | None:
    scope = DataScope(principal.tenant_id, frozenset({team_id}))
    return DataRepository(session, scope).get_snapshot(team_id, snapshot_id)


def _checkpoint(session, run: InvestigationRun):
    session.add(InvestigationCheckpoint(run_id=run.run_id, version=run.version, state=run.state, created_at=_now()))


def create_run(session, principal: Principal, *, team_id: str, snapshot_id: str, idempotency_key: str, cycle_limit: int):
    if not valid_id(team_id) or not valid_id(snapshot_id) or not principal.can(Permission.INVESTIGATION_RUN, team_id):
        raise FlowError(403, "FORBIDDEN_SCOPE")
    if not isinstance(cycle_limit, int) or isinstance(cycle_limit, bool) or not 1 <= cycle_limit <= 20:
        raise FlowError(422, "INVALID_RUN")
    if _snapshot(session, principal, team_id, snapshot_id) is None:
        raise FlowError(404, "NOT_FOUND")
    fingerprint = sha256(f"{snapshot_id}|{cycle_limit}".encode()).hexdigest()
    existing = session.scalar(select(InvestigationRun).where(
        InvestigationRun.tenant_id == principal.tenant_id, InvestigationRun.team_id == team_id,
        InvestigationRun.idempotency_key == idempotency_key,
    ))
    if existing is not None:
        if existing.fingerprint != fingerprint:
            raise FlowError(409, "IDEMPOTENCY_CONFLICT")
        return existing
    run = InvestigationRun(
        run_id=str(uuid4()), tenant_id=principal.tenant_id, team_id=team_id, snapshot_id=snapshot_id,
        idempotency_key=idempotency_key, fingerprint=fingerprint, state="CREATED", version=0, cycle_count=0,
        cycle_limit=cycle_limit, trace_id=current_trace_id(), failure=None, report=None, forecast=None,
        created_by=principal.user_id, created_at=_now(), updated_at=_now(),
    )
    session.add(run)
    _checkpoint(session, run)
    _audit(session, principal, "investigation.create", "investigation", run.run_id, team_id, state="CREATED")
    session.flush()
    return run


def _history(session, run: InvestigationRun):
    row = session.scalar(select(DataImport).where(
        DataImport.tenant_id == run.tenant_id, DataImport.snapshot_id == run.snapshot_id, DataImport.status == "complete",
    ))
    if row is None:
        return [], {}
    observations = []
    for item in row.history or []:
        quantity = None if item.get("quantity") is None else Decimal(item["quantity"])
        observations.append((date.fromisoformat(item["start"]), date.fromisoformat(item["end"]), quantity))
    return observations, row.aggregates or {}


def _inputs(snapshot: SnapshotData, aggregates: dict):
    matrix = prepare_matrix(snapshot.capacity, snapshot.demand)
    if any(pool.available_hours is None or pool.available_hours != pool.available_hours.to_integral_value() for pool in matrix.pools):
        return None
    if any(row.eligible_hours is None or row.eligible_hours != row.eligible_hours.to_integral_value() for row in matrix.rows):
        return None
    pools = {pool.pool_id: int(pool.available_hours) for pool in matrix.pools}
    rows = [Row(row.skill_id, row.shift_id, tuple(row.pool_ids), int(row.eligible_hours)) for row in matrix.rows]
    rate = Decimal(aggregates["cases_per_hour"]) if aggregates.get("cases_per_hour") else None
    if rate is None or any(quantity is None for _, quantity in matrix.demand):
        return pools, rows, None
    demand = {}
    for skill, quantity in matrix.demand:
        demand[skill] = demand.get(skill, 0) + int((quantity / rate).to_integral_value(rounding=ROUND_CEILING))
    return pools, rows, demand


def _policy(session, run, on_date):
    resolution = resolve(
        session, tenant_id=run.tenant_id, team_id=run.team_id, employee_category=None, on_date=on_date,
        rule_keys=list(CATALOG), data_snapshot_id=run.snapshot_id,
    )
    weekly = None
    for item in resolution.items:
        if item.status == "resolved" and item.rule_key == "workweek.max_hours":
            hours = item.parameters.max_hours
            if hours == hours.to_integral_value():
                weekly = int(hours)
    versions = [item.version_id for item in resolution.items if item.version_id]
    dependencies = [f"{item.rule_key}:{item.reason}" for item in resolution.items if item.status != "resolved"]
    return resolution.complete, weekly, versions, dependencies


def _pending(report: dict | None) -> bool:
    return bool(report) and any(question["status"] == "pending" for question in report.get("questions", []))


def _move(session, run, state):
    run.state = state
    run.version += 1
    run.updated_at = _now()
    _checkpoint(session, run)


def step(session, principal: Principal, run_id: str) -> InvestigationRun:
    run = _run(session, principal, run_id)
    if not principal.can(Permission.INVESTIGATION_RUN, run.team_id):
        raise FlowError(403, "FORBIDDEN_SCOPE")
    if run.state in PAUSE and run.state != "WAITING_INPUT":
        return run
    if run.state == "WAITING_INPUT":
        if _pending(run.report):
            return run
        _move(session, run, "PLANNING")
        return run
    if run.state == "CREATED":
        _move(session, run, "VALIDATING")
    elif run.state == "VALIDATING":
        if _snapshot(session, principal, run.team_id, run.snapshot_id) is None:
            run.failure = "SNAPSHOT_MISSING"
            _move(session, run, "FAILED")
        else:
            _move(session, run, "INVESTIGATING")
    elif run.state == "INVESTIGATING":
        _investigate(session, principal, run)
        _move(session, run, "WAITING_INPUT" if _pending(run.report) else "PLANNING")
    elif run.state == "PLANNING":
        _plan(session, principal, run)
        _move(session, run, "SIMULATING")
    elif run.state == "SIMULATING":
        _move(session, run, "REVIEWING")
    elif run.state == "REVIEWING":
        _review(session, principal, run)
    session.flush()
    return run


def advance(session, principal, run_id: str) -> InvestigationRun:
    run = _run(session, principal, run_id)
    for _ in range(30):
        run = step(session, principal, run_id)
        if run.state in PAUSE:
            return run
    run.failure = "STEP_BUDGET"
    _move(session, run, "FAILED")
    session.flush()
    return run


def _investigate(session, principal, run: InvestigationRun):
    if run.report is not None:
        return
    snapshot = _snapshot(session, principal, run.team_id, run.snapshot_id)
    observations, _aggregates = _history(session, run)
    if not observations:
        observations = [(
            snapshot.capacity.period.start, snapshot.capacity.period.end_exclusive,
            None if snapshot.demand.records[0].quantity is None else Decimal(str(snapshot.demand.records[0].quantity)),
        )]
    forecast = forecast_series(
        tenant_id=run.tenant_id, team_id=run.team_id, data_snapshot_id=run.snapshot_id,
        timezone=snapshot.capacity.period.timezone, observations=observations,
    )
    demand_known = any(record.quantity is not None for record in snapshot.demand.records)
    report = build_report(
        tenant_id=run.tenant_id, team_id=run.team_id, data_snapshot_id=run.snapshot_id, demand_known=demand_known,
        history_points=len([item for item in observations if item[2] is not None]), notes=list(snapshot.capacity.limitations),
    )
    run.report = json.loads(report.model_dump_json())
    run.forecast = json.loads(forecast.model_dump_json())
    stored = session.scalar(select(ForecastRow).where(
        ForecastRow.tenant_id == run.tenant_id, ForecastRow.team_id == run.team_id, ForecastRow.snapshot_id == run.snapshot_id,
    ))
    if stored is None:
        session.add(ForecastRow(
            forecast_id=str(uuid4()), tenant_id=run.tenant_id, team_id=run.team_id, snapshot_id=run.snapshot_id,
            payload=run.forecast, created_at=_now(),
        ))


def _plan(session, principal, run: InvestigationRun):
    if session.scalar(select(ScenarioRow.scenario_id).where(ScenarioRow.run_id == run.run_id)) is not None:
        return
    snapshot = _snapshot(session, principal, run.team_id, run.snapshot_id)
    _observations, aggregates = _history(session, run)
    parsed = _inputs(snapshot, aggregates)
    pools, rows, demand = (None, [], None) if parsed is None else parsed
    complete, weekly, versions, dependencies = _policy(session, run, snapshot.capacity.period.start)
    forecast = ForecastResult.model_validate_json(json.dumps(run.forecast))
    # Re-check every operational date in the forecast window. An approved rule
    # valid at snapshot time is not automatically valid for future schedules.
    initial_versions = set(versions)
    if forecast.points:
        day = forecast.horizon.start
        while day < forecast.horizon.end_exclusive:
            effective, effective_weekly, future_versions, future_dependencies = _policy(session, run, day)
            if not effective or effective_weekly != weekly or set(future_versions) != initial_versions:
                complete = False
                dependencies.append(f"revisão jurídica temporal requerida em {day.isoformat()}")
                dependencies.extend(future_dependencies)
                break
            day += timedelta(days=1)
    pairs = build_scenarios(
        tenant_id=run.tenant_id, team_id=run.team_id, snapshot_id=run.snapshot_id,
        pools=pools or {}, rows=rows, demand_hours=demand, weekly_max=weekly, policy_complete=complete,
        forecast_calibrated=forecast.status == "calibrated", dependencies=dependencies, rule_versions=versions,
    )
    for scenario, simulation in pairs:
        session.add(ScenarioRow(
            scenario_id=scenario.scenario_id, run_id=run.run_id, tenant_id=run.tenant_id, team_id=run.team_id,
            snapshot_id=run.snapshot_id, kind=scenario.kind, version=scenario.version, content_hash=scenario.content_hash,
            payload=json.loads(scenario.model_dump_json()),
        ))
        session.add(SimulationRow(
            simulation_id=simulation.simulation_id, scenario_id=scenario.scenario_id, tenant_id=run.tenant_id,
            payload=json.loads(simulation.model_dump_json()),
        ))


def _review(session, principal, run: InvestigationRun):
    already = any(question["question_id"].startswith("q-revision") for question in run.report.get("questions", []))
    snapshot = _snapshot(session, principal, run.team_id, run.snapshot_id)
    complete, _weekly, _versions, _dependencies = _policy(session, run, snapshot.capacity.period.start)
    forecast_status = run.forecast["status"]
    requested = False
    scenarios = list(session.scalars(select(ScenarioRow).where(ScenarioRow.run_id == run.run_id)))
    for scenario_row in scenarios:
        scenario = ScenarioCandidate.model_validate_json(json.dumps(scenario_row.payload))
        simulation_row = session.scalar(select(SimulationRow).where(SimulationRow.scenario_id == scenario_row.scenario_id))
        simulation = SimulationResult.model_validate_json(json.dumps(simulation_row.payload))
        review = critique(
            scenario=scenario, simulation=simulation, policy_complete=complete, forecast_status=forecast_status,
            already_asked=already,
        )
        requested = requested or review.revision_requested
        existing = session.scalar(select(CriticRow).where(CriticRow.scenario_id == scenario_row.scenario_id))
        payload = json.loads(review.model_dump_json())
        if existing is None:
            session.add(CriticRow(review_id=review.review_id, scenario_id=scenario_row.scenario_id,
                                  tenant_id=run.tenant_id, payload=payload))
        else:
            existing.payload = payload
    if requested:
        if run.cycle_count + 1 > run.cycle_limit:
            run.failure = "CYCLE_LIMIT"
            _move(session, run, "BLOCKED")
            return
        run.cycle_count += 1
        questions = list(run.report["questions"])
        questions.append({
            "question_id": f"q-revision-{run.cycle_count}",
            "text": "O histórico curto muda a leitura do déficit de capacidade?",
            "status": "pending", "answer": None,
        })
        run.report = {**run.report, "questions": questions}
        _move(session, run, "WAITING_INPUT")
        return
    _move(session, run, "AWAITING_HUMAN")


def answer(session, principal: Principal, run_id: str, *, question_id: str, text: str, idempotency_key: str):
    run = _run(session, principal, run_id)
    if not principal.can(Permission.INVESTIGATION_ANSWER, run.team_id):
        raise FlowError(403, "FORBIDDEN_SCOPE")
    if run.state != "WAITING_INPUT" or not run.report:
        raise FlowError(409, "INVALID_STATE")
    if not isinstance(text, str) or not text.strip() or text != text.strip() or len(text) > 2000:
        raise FlowError(422, "INVALID_ANSWER")
    report = InvestigationReport.model_validate_json(json.dumps(run.report))
    if question_id not in {question.question_id for question in report.questions}:
        raise FlowError(404, "NOT_FOUND")
    existing = session.scalar(select(InvestigationAnswer).where(
        InvestigationAnswer.run_id == run.run_id, InvestigationAnswer.question_id == question_id,
    ))
    if existing is not None:
        if existing.idempotency_key == idempotency_key and existing.answer == text:
            return run
        raise FlowError(409, "IDEMPOTENCY_CONFLICT")
    try:
        updated = apply_answer(report, question_id, text)
    except KeyError:
        raise FlowError(404, "NOT_FOUND") from None
    run.report = json.loads(updated.model_dump_json())
    run.updated_at = _now()
    session.add(InvestigationAnswer(
        answer_id=str(uuid4()), run_id=run.run_id, question_id=question_id, idempotency_key=idempotency_key,
        answer=text, created_at=_now(),
    ))
    _audit(session, principal, "investigation.answer", "investigation", run.run_id, run.team_id, question_id=question_id)
    session.flush()
    return run


def allow_revision(cycle_count: int, cycle_limit: int) -> bool:
    return cycle_count + 1 <= cycle_limit
