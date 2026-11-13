"""Record a human decision. A draft is a separate, explicit request and never leaves the system."""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.audit.log import record_event
from backend.app.auth.permissions import Permission, Principal
from backend.app.flow.errors import FlowError
from backend.app.flow.models import CriticRow, DecisionRow, InvestigationRun, RequisitionDraftRow, ScenarioRow, SimulationRow
from backend.app.planning.schemas import DecisionRecord, RequisitionDraft
from backend.app.policies.models import PolicyVersion


def _audit(session, principal, action, resource_id, team_id, **details):
    record_event(
        session, action=action, outcome="success", tenant_id=principal.tenant_id, actor_user_id=principal.user_id,
        team_id=team_id, resource_type="decision", resource_id=resource_id, details=details,
    )


def _scenario(session, principal: Principal, scenario_id: str) -> ScenarioRow:
    row = session.get(ScenarioRow, scenario_id)
    if row is None or row.tenant_id != principal.tenant_id or not principal.can(Permission.SCENARIO_READ, row.team_id):
        raise FlowError(404, "NOT_FOUND")
    return row


def decide(session: Session, principal: Principal, scenario_id: str, *, decision: str, reason: str,
           expected_hash: str, idempotency_key: str) -> DecisionRow:
    if not principal.can(Permission.DECISION_WRITE, None) and not _can_decide(principal, session, scenario_id):
        raise FlowError(403, "FORBIDDEN_SCOPE")
    row = session.get(ScenarioRow, scenario_id)
    if row is None or row.tenant_id != principal.tenant_id or not principal.can(Permission.DECISION_WRITE, row.team_id):
        raise FlowError(404 if row is None or row.tenant_id != principal.tenant_id else 403, "FORBIDDEN_SCOPE" if row and row.tenant_id == principal.tenant_id else "NOT_FOUND", getattr(row, "team_id", None))
    if expected_hash != row.content_hash:
        raise FlowError(409, "MATERIAL_CHANGE", row.team_id)
    if decision == "approve":
        run = session.scalar(select(InvestigationRun).where(
            InvestigationRun.run_id == row.run_id,
        ).with_for_update())
        if run is None or run.tenant_id != row.tenant_id or row.version != run.cycle_count + 1:
            raise FlowError(409, "MATERIAL_CHANGE", row.team_id)
    existing = session.scalar(select(DecisionRow).where(DecisionRow.scenario_id == scenario_id))
    if existing is not None:
        if existing.idempotency_key == idempotency_key and existing.decision == decision and existing.reason == reason:
            return existing
        raise FlowError(409, "IDEMPOTENCY_CONFLICT", row.team_id)
    if decision == "approve":
        for version_id in row.payload.get("rule_versions") or []:
            version = session.get(PolicyVersion, version_id)
            if version is None or version.tenant_id != row.tenant_id or version.status != "approved":
                raise FlowError(409, "MATERIAL_CHANGE", row.team_id)
        if (row.payload.get("quantitative") or {}).get("simulation_only"):
            raise FlowError(409, "NOT_CONCLUSIVE", row.team_id)
        # The v4.1 `conclusive` flag is not independent evidence of legal,
        # mandatory coverage or qualification checks. Refuse all new v4.2
        # approvals unless a deterministic verifier has written a valid result.
        verified = row.payload.get("v42_validation")
        if not (isinstance(verified, dict)
                and verified.get("status") == "valid"
                and verified.get("mandatory_coverage_met") is True
                and not verified.get("violations")):
            raise FlowError(409, "NOT_CONCLUSIVE", row.team_id)
        simulation = session.scalar(select(SimulationRow).where(SimulationRow.scenario_id == scenario_id))
        review = session.scalar(select(CriticRow).where(CriticRow.scenario_id == scenario_id))
        if (not row.payload.get("conclusive") or simulation is None or simulation.payload.get("status") not in {"optimal", "feasible"}
                or (row.kind == "hire" and (row.payload.get("residual_hours") is None or row.payload.get("residual_hours") > 0))
                or review is None or review.payload.get("verdict") == "blocked" or review.payload.get("hard_constraint_failed")):
            raise FlowError(409, "NOT_CONCLUSIVE", row.team_id)
    record = DecisionRecord.model_validate({
        "schema_version": "1.0", "decision_id": str(uuid4()), "scenario_id": scenario_id, "tenant_id": row.tenant_id,
        "team_id": row.team_id, "data_snapshot_id": row.snapshot_id, "scenario_hash": row.content_hash,
        "rule_versions": list(row.payload.get("rule_versions") or []), "decision": decision, "reason": reason,
        "actor_user_id": principal.user_id, "decided_at": datetime.now(timezone.utc), "executed": False,
    })
    stored = DecisionRow(
        decision_id=record.decision_id, scenario_id=scenario_id, tenant_id=row.tenant_id, actor_user_id=principal.user_id,
        idempotency_key=idempotency_key, scenario_hash=row.content_hash, decision=decision, reason=reason,
        created_at=record.decided_at,
    )
    session.add(stored)
    _audit(session, principal, "decision.record", stored.decision_id, row.team_id, decision=decision, scenario_id=scenario_id)
    session.flush()
    return stored


def _can_decide(principal, session, scenario_id) -> bool:
    row = session.get(ScenarioRow, scenario_id)
    return row is not None and principal.can(Permission.DECISION_WRITE, row.team_id)


def draft(session: Session, principal: Principal, scenario_id: str, *, idempotency_key: str) -> RequisitionDraftRow:
    row = session.get(ScenarioRow, scenario_id)
    if row is None or row.tenant_id != principal.tenant_id:
        raise FlowError(404, "NOT_FOUND")
    if not principal.can(Permission.REQUISITION_DRAFT, row.team_id):
        raise FlowError(403, "FORBIDDEN_SCOPE", row.team_id)
    run = session.get(InvestigationRun, row.run_id)
    if run is None or run.tenant_id != row.tenant_id or row.version != run.cycle_count + 1:
        raise FlowError(409, "MATERIAL_CHANGE", row.team_id)
    decision = session.scalar(select(DecisionRow).where(DecisionRow.scenario_id == scenario_id))
    if decision is None or decision.decision != "approve":
        raise FlowError(409, "NOT_APPROVED", row.team_id)
    existing = session.scalar(select(RequisitionDraftRow).where(RequisitionDraftRow.decision_id == decision.decision_id))
    if existing is not None:
        if existing.idempotency_key == idempotency_key:
            return existing
        raise FlowError(409, "IDEMPOTENCY_CONFLICT", row.team_id)
    payload = RequisitionDraft.model_validate({
        "schema_version": "1.0", "draft_id": str(uuid4()), "decision_id": decision.decision_id,
        "tenant_id": row.tenant_id, "team_id": row.team_id,
        "summary": f"Rascunho interno do cenário {row.kind}. Sem efeito administrativo e sem operação externa.",
        "limitations": list(row.payload.get("gaps") or []) + ["Aprovação do cenário não autoriza contratação nem integração externa."],
        "executed": False,
    })
    stored = RequisitionDraftRow(
        draft_id=payload.draft_id, decision_id=decision.decision_id, tenant_id=row.tenant_id,
        idempotency_key=idempotency_key, payload=payload.model_dump(mode="json"), executed=0,
    )
    session.add(stored)
    _audit(session, principal, "requisition.draft", stored.draft_id, row.team_id, decision_id=decision.decision_id)
    session.flush()
    return stored
