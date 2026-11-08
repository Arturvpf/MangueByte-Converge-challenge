"""Policy Store HTTP API. Tenant comes from the principal."""
from datetime import date, datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import ValidationError

from backend.app.audit.log import record_event
from backend.app.auth.dependencies import deny, require_permission
from backend.app.auth.permissions import Permission, Principal
from backend.app.policies.models import PolicyCatalogError, PolicyConflictError, PolicyImmutableError
from backend.app.policies.resolver import resolve
from backend.app.policies.schemas import (
    ApproveIn, PolicyCreate, PolicyDetail, PolicyList, PolicyListQuery, PolicyOut, PolicyResolution, PolicyVersionOut,
    RejectIn, ResolveQuery, RevokeIn, RevisionCommand, VersionCreate, VersionUpdate,
)
from backend.app.policies.service import (
    IdempotencyConflict, InvalidTransition, PolicyForbidden, PolicyNotFound, StaleRevision,
    approve_version, create_policy, create_version, get_policy, get_version, list_policies,
    reject_version, revoke_version, submit_version, update_draft,
)

router = APIRouter(prefix="/api/policies", tags=["policies"])
reader = require_permission(Permission.POLICY_READ)


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _policy_out(policy) -> PolicyOut:
    return PolicyOut.model_validate({
        "policy_id": policy.policy_id, "tenant_id": policy.tenant_id, "rule_key": policy.rule_key,
        "category": policy.category, "team_id": policy.team_id, "employee_category": policy.employee_category,
        "title": policy.title, "created_by": policy.created_by, "created_at": _utc(policy.created_at),
    })


def _version_out(policy, version) -> PolicyVersionOut:
    names = (
        "version_id", "policy_id", "version", "status", "parameters", "source_kind", "source_reference",
        "valid_from", "valid_until", "content_hash", "revision", "author_user_id", "submitted_by",
        "approved_by", "legal_review_reference", "review_note", "revoked_by", "revocation_reason",
    )
    payload = {name: getattr(version, name) for name in names}
    for name in ("created_at", "submitted_at", "approved_at", "revoked_at"):
        payload[name] = _utc(getattr(version, name))
    return PolicyVersionOut.model_validate(payload)


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, PolicyNotFound):
        return HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Policy not found"})
    if isinstance(exc, StaleRevision):
        return HTTPException(status_code=409, detail={"code": "STALE_REVISION", "message": "Stale revision"})
    if isinstance(exc, (InvalidTransition, PolicyConflictError, PolicyImmutableError)):
        code = "SCOPE_CONFLICT" if isinstance(exc, PolicyConflictError) else "INVALID_TRANSITION"
        return HTTPException(status_code=409, detail={"code": code, "message": exc.__class__.__name__})
    if isinstance(exc, IdempotencyConflict):
        return HTTPException(status_code=409, detail={"code": "IDEMPOTENCY_CONFLICT", "message": "Idempotency key reused"})
    if isinstance(exc, (PolicyCatalogError, ValidationError)):
        return HTTPException(status_code=422, detail={"code": "INVALID_POLICY", "message": "Invalid policy content"})
    raise exc


def _key(value: str | None) -> str | None:
    if value is None:
        return None
    if not value or value != value.strip() or len(value) > 128:
        raise HTTPException(status_code=422, detail={"code": "INVALID_POLICY", "message": "Invalid idempotency key"})
    return value


def _call(request: Request, principal: Principal, fn):
    try:
        with request.app.state.session_factory() as session:
            result = fn(session)
            session.commit()
            return result
    except PolicyForbidden as exc:
        permission = exc.args[0] if exc.args and isinstance(exc.args[0], Permission) else Permission.POLICY_APPROVE
        deny(request, principal, permission)
    except (PolicyNotFound, StaleRevision, InvalidTransition, IdempotencyConflict, PolicyConflictError,
            PolicyImmutableError, PolicyCatalogError, ValidationError) as exc:
        raise _http(exc) from None


@router.get("", response_model=PolicyList)
def list_route(
    request: Request, principal: Principal = Depends(reader), rule_key: str | None = None,
    category: str | None = None, team_id: str | None = None, status: str | None = None,
):
    try:
        filters = PolicyListQuery.model_validate({
            "rule_key": rule_key, "category": category, "team_id": team_id, "status": status,
        })
    except ValidationError as exc:
        raise _http(exc) from None
    policies = _call(request, principal, lambda session: list_policies(
        session, principal, rule_key=filters.rule_key, category=filters.category,
        team_id=filters.team_id, status=filters.status,
    ))
    return PolicyList(items=[_policy_out(item) for item in policies])


@router.post("", response_model=PolicyDetail)
def create_route(
    body: PolicyCreate, request: Request, principal: Principal = Depends(reader),
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    key = _key(idempotency_key)

    def run(session):
        policy, version = create_policy(session, principal, body, key)
        return _policy_out(policy), _version_out(policy, version)

    policy, version = _call(request, principal, run)
    return PolicyDetail(**policy.model_dump(), versions=[version])


@router.get("/resolve", response_model=PolicyResolution)
def resolve_route(
    request: Request, on_date: date, team_id: str, principal: Principal = Depends(reader),
    employee_category: str | None = None, rule_keys: Annotated[list[str], Query()] = (),
):
    try:
        query = ResolveQuery.model_validate({
            "on_date": on_date, "team_id": team_id, "employee_category": employee_category, "rule_keys": list(rule_keys),
        })
    except ValidationError as exc:
        raise _http(exc) from None
    if not principal.can(Permission.POLICY_READ, query.team_id):
        deny(request, principal, Permission.POLICY_READ, query.team_id)

    def run(session):
        result = resolve(
            session, tenant_id=principal.tenant_id, team_id=query.team_id, employee_category=query.employee_category,
            on_date=query.on_date, rule_keys=query.rule_keys, data_snapshot_id="api",
        )
        record_event(
            session, action="policy.resolve", outcome="success", tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id, team_id=query.team_id, resource_type="policy", resource_id=query.team_id,
            details={"outcome_reason": "complete" if result.complete else "review_required", "rules": len(result.items)},
        )
        return result

    return _call(request, principal, run)


@router.get("/{policy_id}", response_model=PolicyDetail)
def detail_route(policy_id: str, request: Request, principal: Principal = Depends(reader)):
    policy, versions = _call(request, principal, lambda session: get_policy(session, principal, policy_id))
    return PolicyDetail(**_policy_out(policy).model_dump(), versions=[_version_out(policy, item) for item in versions])


@router.post("/{policy_id}/versions", response_model=PolicyVersionOut)
def version_route(
    policy_id: str, body: VersionCreate, request: Request, principal: Principal = Depends(reader),
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    key = _key(idempotency_key)
    policy, version = _call(request, principal, lambda session: create_version(session, principal, policy_id, body, key))
    return _version_out(policy, version)


@router.get("/{policy_id}/versions/{version_id}", response_model=PolicyVersionOut)
def read_version_route(policy_id: str, version_id: str, request: Request, principal: Principal = Depends(reader)):
    policy, version = _call(request, principal, lambda session: get_version(session, principal, version_id))
    if policy.policy_id != policy_id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Policy not found"})
    return _version_out(policy, version)


@router.patch("/{policy_id}/versions/{version_id}", response_model=PolicyVersionOut)
def patch_route(policy_id: str, version_id: str, body: VersionUpdate, request: Request, principal: Principal = Depends(reader)):
    policy, version = _call(request, principal, lambda session: update_draft(session, principal, version_id, body))
    if policy.policy_id != policy_id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Policy not found"})
    return _version_out(policy, version)


def _command(request, principal, version_id, fn):
    return _call(request, principal, lambda session: fn(session))


@router.post("/{policy_id}/versions/{version_id}/submit", response_model=PolicyVersionOut)
def submit_route(policy_id: str, version_id: str, body: RevisionCommand, request: Request, principal: Principal = Depends(reader)):
    policy, version = _command(request, principal, version_id, lambda session: submit_version(session, principal, version_id, body.expected_revision))
    return _version_out(policy, version)


@router.post("/{policy_id}/versions/{version_id}/reject", response_model=PolicyVersionOut)
def reject_route(policy_id: str, version_id: str, body: RejectIn, request: Request, principal: Principal = Depends(reader)):
    policy, version = _command(request, principal, version_id, lambda session: reject_version(
        session, principal, version_id, body.expected_revision, body.review_note))
    return _version_out(policy, version)


@router.post("/{policy_id}/versions/{version_id}/approve", response_model=PolicyVersionOut)
def approve_route(policy_id: str, version_id: str, body: ApproveIn, request: Request, principal: Principal = Depends(reader)):
    policy, version = _command(request, principal, version_id, lambda session: approve_version(
        session, principal, version_id, body.expected_revision, body.legal_review_reference))
    return _version_out(policy, version)


@router.post("/{policy_id}/versions/{version_id}/revoke", response_model=PolicyVersionOut)
def revoke_route(policy_id: str, version_id: str, body: RevokeIn, request: Request, principal: Principal = Depends(reader)):
    policy, version = _command(request, principal, version_id, lambda session: revoke_version(
        session, principal, version_id, body.expected_revision, body.revocation_reason))
    return _version_out(policy, version)
