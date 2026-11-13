"""Incorporate a verified aggregate snapshot as a new, immutable scenario cycle."""
from sqlalchemy import select, update

from backend.app.auth.permissions import Permission
from backend.app.flow.errors import FlowError
from backend.app.flow.models import InvestigationRun, PlanningEvidence
from backend.app.workflow.service import _audit, _move, _now, _run, _snapshot, advance


def replan(session, principal, run_id, *, snapshot_id, expected_version, idempotency_key, reason, premises):
    run = _run(session, principal, run_id)
    if not principal.can(Permission.DECISION_WRITE, run.team_id):
        raise FlowError(403, "FORBIDDEN_SCOPE", run.team_id)
    # The CAS serializes revisions on both supported databases, including
    # SQLite where SELECT FOR UPDATE has no effect.
    existing = session.get(PlanningEvidence, (run_id, idempotency_key))
    previous_evidence = session.scalar(select(PlanningEvidence).where(
        PlanningEvidence.run_id == run_id,
    ).order_by(PlanningEvidence.created_at.desc()).limit(1))
    provided = premises.model_dump(mode="json") if premises is not None else None
    request = dict(snapshot_id=snapshot_id, expected_version=expected_version, reason=reason, premises=provided)
    if existing is not None:
        if existing.payload["request"] != request:
            raise FlowError(409, "IDEMPOTENCY_CONFLICT")
        return run
    if run.version != expected_version or run.state not in {"AWAITING_HUMAN", "WAITING_INPUT", "BLOCKED"}:
        raise FlowError(409, "MATERIAL_CHANGE")
    if run.cycle_count >= run.cycle_limit:
        raise FlowError(409, "CYCLE_LIMIT")
    source = _snapshot(session, principal, run.team_id, snapshot_id)
    if source is None:
        raise FlowError(404, "NOT_FOUND")
    current_premises = previous_evidence.payload["request"].get("premises") if previous_evidence else None
    if snapshot_id == run.snapshot_id and (provided is None or provided == current_premises):
        raise FlowError(409, "EVIDENCE_UNCHANGED")
    if premises is not None and not premises.applies_to(source):
        raise FlowError(422, "PREMISES_OUTSIDE_SNAPSHOT")
    acquired = session.execute(update(InvestigationRun).where(
        InvestigationRun.run_id == run_id, InvestigationRun.version == expected_version,
    ).values(updated_at=_now())).rowcount
    if acquired != 1:
        raise FlowError(409, "MATERIAL_CHANGE")
    previous = run.snapshot_id
    session.add(PlanningEvidence(
        run_id=run_id, idempotency_key=idempotency_key, actor_user_id=principal.user_id, created_at=_now(),
        payload={"request": request, "previous_snapshot_id": previous, "cycle": run.cycle_count + 2,
                 "source_kind": source.source.kind, "classification": "reviewed_snapshot"},
    ))
    run.snapshot_id = snapshot_id
    run.cycle_count += 1
    run.report = run.forecast = run.failure = None
    _move(session, run, "INVESTIGATING")
    _audit(session, principal, "investigation.replan", "investigation", run_id, run.team_id,
           previous_snapshot_id=previous, snapshot_id=snapshot_id, cycle=run.cycle_count + 1)
    session.flush()
    return advance(session, principal, run_id)


def list_evidence(session, principal, run_id):
    run = _run(session, principal, run_id)
    if not principal.can(Permission.DECISION_WRITE, run.team_id):
        raise FlowError(403, "FORBIDDEN_SCOPE", run.team_id)
    records = session.scalars(select(PlanningEvidence).where(
        PlanningEvidence.run_id == run_id,
    ).order_by(PlanningEvidence.created_at))
    return {"items": [item.payload for item in records]}
