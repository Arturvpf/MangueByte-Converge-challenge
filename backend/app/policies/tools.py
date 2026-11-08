"""Typed policy tool for agents. A partial rule set is never returned."""
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from backend.app.audit.log import record_event
from backend.app.audit.tracing import current_trace_id
from backend.app.auth.permissions import Permission, Principal
from backend.app.auth.tools import ToolForbidden, authorize_tool
from backend.app.contracts.v1 import ContractError, ErrorCode, ToolRequest, ToolResponse
from backend.app.policies.resolver import resolve, resolve_pinned
from backend.app.policies.schemas import PolicyResolution


def _detail(item) -> str:
    reason = item.reason or "review_required"
    if item.rule_key is None:
        return reason
    return f"{item.rule_key}:{reason}"


def _envelope(request: ToolRequest, *, status: str, result: PolicyResolution | None, error: ContractError | None,
              rule_versions: list[str]) -> ToolResponse[PolicyResolution]:
    return ToolResponse[PolicyResolution].model_validate({
        "schema_version": "1.0", "tenant_id": request.tenant_id, "team_id": request.team_id, "status": status,
        "result": result, "error": error, "evidence_refs": [], "data_version": request.data_snapshot_id,
        "model_version": None, "rule_versions": rule_versions, "generated_at": datetime.now(timezone.utc),
        "limitations": [], "trace_id": current_trace_id(),
    })


def _forbidden(request: ToolRequest) -> ToolResponse[PolicyResolution]:
    error = ContractError(code=ErrorCode.FORBIDDEN_SCOPE, message="Scope denied", retryable=False, details=[])
    return _envelope(request, status="error", result=None, error=error, rule_versions=[])


def get_applicable_policies(session: Session, principal: Principal, request: ToolRequest, *, on_date: date,
                            employee_category: str | None, rule_keys: list[str]) -> ToolResponse[PolicyResolution]:
    try:
        authorize_tool(principal, Permission.POLICY_READ, tenant_id=request.tenant_id, team_id=request.team_id)
    except ToolForbidden:
        record_event(
            session, action="policy.resolve", outcome="denied", tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id, resource_type="policy", resource_id=principal.tenant_id,
            details={"outcome_reason": "forbidden"},
        )
        session.flush()
        return _forbidden(request)
    if request.policy_version_ids:
        resolution = resolve_pinned(
            session, tenant_id=principal.tenant_id, team_id=request.team_id, on_date=on_date,
            version_ids=list(request.policy_version_ids), data_snapshot_id=request.data_snapshot_id,
        )
    else:
        resolution = resolve(
            session, tenant_id=principal.tenant_id, team_id=request.team_id, employee_category=employee_category,
            on_date=on_date, rule_keys=rule_keys, data_snapshot_id=request.data_snapshot_id,
        )
    record_event(
        session, action="policy.resolve", outcome="success", tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id, team_id=request.team_id, resource_type="policy",
        resource_id=request.team_id, details={
            "outcome_reason": "complete" if resolution.complete else "review_required", "rules": len(resolution.items),
        },
    )
    session.flush()
    if not resolution.complete:
        error = ContractError(
            code=ErrorCode.POLICY_REVIEW_REQUIRED, message="Policy review required", retryable=False,
            details=[_detail(item) for item in resolution.items if item.status != "resolved"],
        )
        return _envelope(request, status="error", result=None, error=error, rule_versions=[])
    return _envelope(
        request, status="ok", result=resolution, error=None,
        rule_versions=[item.version_id for item in resolution.items if item.version_id],
    )
