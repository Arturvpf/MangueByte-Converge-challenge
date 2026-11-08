"""Policy lifecycle. No FastAPI. The caller commits the session."""
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.audit.log import record_event
from backend.app.auth.permissions import Permission, Principal
from backend.app.policies.catalog import UnknownRuleKey, category_for, validate_parameters
from backend.app.policies.models import Policy, PolicyCatalogError, PolicyConflictError, PolicyVersion
from backend.app.policies.schemas import PolicyCreate, VersionCreate, VersionUpdate


class PolicyServiceError(Exception):
    code = "POLICY_ERROR"


class PolicyForbidden(PolicyServiceError):
    code = "FORBIDDEN_SCOPE"


class PolicyNotFound(PolicyServiceError):
    code = "NOT_FOUND"


class StaleRevision(PolicyServiceError):
    code = "STALE_REVISION"


class InvalidTransition(PolicyServiceError):
    code = "INVALID_TRANSITION"


class IdempotencyConflict(PolicyServiceError):
    code = "IDEMPOTENCY_CONFLICT"


def _jsonable(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def content_hash(*, parameters, source_kind: str, source_reference: str, valid_from, valid_until) -> str:
    payload = {
        "parameters": _jsonable(parameters),
        "source_kind": source_kind,
        "source_reference": source_reference,
        "valid_from": valid_from.isoformat(),
        "valid_until": None if valid_until is None else valid_until.isoformat(),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256(raw.encode()).hexdigest()


def _scope_allowed(principal: Principal, permission: Permission, team_id: str | None) -> bool:
    if team_id is None:
        return principal.tenant_wide(permission)
    return principal.can(permission, team_id)


def _require(principal: Principal, permission: Permission, team_id: str | None) -> None:
    if not _scope_allowed(principal, permission, team_id):
        raise PolicyForbidden(permission)


def visible(principal: Principal):
    """Policies of this company the principal may read."""
    clauses = [Policy.tenant_id == principal.tenant_id]
    if not principal.tenant_wide(Permission.POLICY_READ):
        teams = principal.team_ids(Permission.POLICY_READ)
        clauses.append((Policy.team_id.is_(None)) | (Policy.team_id.in_(teams)))
    return clauses


def _audit(session, principal: Principal, action: str, resource_type: str, resource_id: str,
           team_id: str | None, **details) -> None:
    record_event(
        session, action=action, outcome="success", tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id, team_id=team_id, resource_type=resource_type,
        resource_id=resource_id, details=details,
    )


def _stored_parameters(parameters) -> dict:
    model = parameters if hasattr(parameters, "model_dump") else None
    return _jsonable(model if model is not None else parameters)


def _same_create(version: PolicyVersion, policy: Policy, body: PolicyCreate) -> bool:
    digest = content_hash(
        parameters=body.parameters, source_kind=body.source_kind, source_reference=body.source_reference,
        valid_from=body.valid_from, valid_until=body.valid_until,
    )
    return (
        version.content_hash == digest and policy.rule_key == body.rule_key and policy.team_id == body.team_id
        and policy.employee_category == body.employee_category and policy.title == body.title
    )


def _find_idempotent(session: Session, tenant_id: str, key: str) -> tuple[Policy, PolicyVersion] | None:
    version = session.scalar(select(PolicyVersion).where(
        PolicyVersion.tenant_id == tenant_id, PolicyVersion.idempotency_key == key,
    ))
    if version is None:
        return None
    policy = session.get(Policy, version.policy_id)
    return policy, version


def create_policy(session: Session, principal: Principal, body: PolicyCreate, idempotency_key: str | None = None):
    _require(principal, Permission.POLICY_WRITE, body.team_id)
    if idempotency_key:
        found = _find_idempotent(session, principal.tenant_id, idempotency_key)
        if found:
            policy, version = found
            if _same_create(version, policy, body):
                return policy, version
            raise IdempotencyConflict("idempotency key reused with different content")
    parameters = _stored_parameters(body.parameters)
    policy = Policy(
        policy_id=str(uuid4()), tenant_id=principal.tenant_id, rule_key=body.rule_key,
        category=category_for(body.rule_key), team_id=body.team_id, employee_category=body.employee_category,
        title=body.title, created_by=principal.user_id,
    )
    version = PolicyVersion(
        version_id=str(uuid4()), policy_id=policy.policy_id, tenant_id=principal.tenant_id, version=1,
        status="draft", parameters=parameters, source_kind=body.source_kind, source_reference=body.source_reference,
        valid_from=body.valid_from, valid_until=body.valid_until,
        content_hash=content_hash(
            parameters=parameters, source_kind=body.source_kind, source_reference=body.source_reference,
            valid_from=body.valid_from, valid_until=body.valid_until,
        ),
        revision=0, author_user_id=principal.user_id, idempotency_key=idempotency_key,
    )
    session.add(policy)
    session.add(version)
    _audit(session, principal, "policy.create", "policy", policy.policy_id, policy.team_id, rule_key=policy.rule_key)
    _audit(session, principal, "policy.version.create", "policy_version", version.version_id, policy.team_id,
           rule_key=policy.rule_key, version=version.version, to_status="draft")
    session.flush()
    return policy, version


def _policy_for_version(session: Session, principal: Principal, version: PolicyVersion) -> Policy:
    policy = session.get(Policy, version.policy_id)
    if policy is None or policy.tenant_id != principal.tenant_id or version.tenant_id != principal.tenant_id:
        raise PolicyNotFound("policy not found")
    if not principal.tenant_wide(Permission.POLICY_READ) and policy.team_id is not None \
            and policy.team_id not in principal.team_ids(Permission.POLICY_READ) \
            and not principal.can(Permission.POLICY_READ, policy.team_id):
        raise PolicyNotFound("policy not found")
    return policy


def get_version(session: Session, principal: Principal, version_id: str) -> tuple[Policy, PolicyVersion]:
    if not principal.has(Permission.POLICY_READ):
        raise PolicyForbidden(Permission.POLICY_READ)
    version = session.get(PolicyVersion, version_id)
    if version is None or version.tenant_id != principal.tenant_id:
        raise PolicyNotFound("policy not found")
    return _policy_for_version(session, principal, version), version


def _expect(version: PolicyVersion, expected_revision: int) -> None:
    if version.revision != expected_revision:
        raise StaleRevision("stale revision")


def update_draft(session: Session, principal: Principal, version_id: str, body: VersionUpdate):
    policy, version = get_version(session, principal, version_id)
    _require(principal, Permission.POLICY_WRITE, policy.team_id)
    _expect(version, body.expected_revision)
    if version.status != "draft":
        raise InvalidTransition("only a draft can be edited")
    parameters = _stored_parameters(body.parameters)
    try:
        validate_parameters(policy.rule_key, parameters)
    except (ValidationError, UnknownRuleKey) as exc:
        raise PolicyCatalogError(str(exc)) from exc
    version.parameters = parameters
    version.source_kind = body.source_kind
    version.source_reference = body.source_reference
    version.valid_from = body.valid_from
    version.valid_until = body.valid_until
    version.content_hash = content_hash(
        parameters=parameters, source_kind=body.source_kind, source_reference=body.source_reference,
        valid_from=body.valid_from, valid_until=body.valid_until,
    )
    version.revision += 1
    _audit(session, principal, "policy.version.update", "policy_version", version.version_id, policy.team_id,
           rule_key=policy.rule_key, version=version.version, from_status="draft", to_status="draft")
    session.flush()
    return policy, version


def create_version(session: Session, principal: Principal, policy_id: str, body: VersionCreate, idempotency_key: str | None = None):
    policy = _readable_policy(session, principal, policy_id)
    _require(principal, Permission.POLICY_WRITE, policy.team_id)
    if body.parameters is None:
        source = session.get(PolicyVersion, body.copy_from_version_id)
        if source is None or source.policy_id != policy.policy_id or source.tenant_id != principal.tenant_id:
            raise PolicyNotFound("policy not found")
        parameters, kind, reference, start, end = (
            dict(source.parameters), source.source_kind, source.source_reference, source.valid_from, source.valid_until,
        )
    else:
        parameters = _stored_parameters(body.parameters)
        try:
            validate_parameters(policy.rule_key, parameters)
        except (ValidationError, UnknownRuleKey) as exc:
            raise PolicyCatalogError(str(exc)) from exc
        kind, reference, start, end = body.source_kind, body.source_reference, body.valid_from, body.valid_until
    digest = content_hash(parameters=parameters, source_kind=kind, source_reference=reference, valid_from=start, valid_until=end)
    if idempotency_key:
        found = _find_idempotent(session, principal.tenant_id, idempotency_key)
        if found:
            existing_policy, existing = found
            if existing.policy_id == policy.policy_id and existing.content_hash == digest:
                return existing_policy, existing
            raise IdempotencyConflict("idempotency key reused with different content")
    number = (session.scalar(select(PolicyVersion.version).where(PolicyVersion.policy_id == policy.policy_id)
                             .order_by(PolicyVersion.version.desc())) or 0) + 1
    version = PolicyVersion(
        version_id=str(uuid4()), policy_id=policy.policy_id, tenant_id=principal.tenant_id, version=number,
        status="draft", parameters=dict(parameters), source_kind=kind, source_reference=reference,
        valid_from=start, valid_until=end,
        content_hash=digest,
        revision=0, author_user_id=principal.user_id, idempotency_key=idempotency_key,
    )
    session.add(version)
    _audit(session, principal, "policy.version.create", "policy_version", version.version_id, policy.team_id,
           rule_key=policy.rule_key, version=number, to_status="draft")
    session.flush()
    return policy, version


def _readable_policy(session: Session, principal: Principal, policy_id: str) -> Policy:
    if not principal.has(Permission.POLICY_READ):
        raise PolicyForbidden(Permission.POLICY_READ)
    policy = session.get(Policy, policy_id)
    if policy is None or policy.tenant_id != principal.tenant_id:
        raise PolicyNotFound("policy not found")
    if policy.team_id is not None and not principal.tenant_wide(Permission.POLICY_READ) \
            and not principal.can(Permission.POLICY_READ, policy.team_id):
        raise PolicyNotFound("policy not found")
    return policy


def list_policies(session: Session, principal: Principal, *, rule_key=None, category=None, team_id=None, status=None):
    if not principal.has(Permission.POLICY_READ):
        raise PolicyForbidden(Permission.POLICY_READ)
    query = select(Policy).where(*visible(principal)).order_by(Policy.rule_key, Policy.policy_id)
    if rule_key is not None:
        query = query.where(Policy.rule_key == rule_key)
    if category is not None:
        query = query.where(Policy.category == category)
    if team_id is not None:
        query = query.where(Policy.team_id == team_id)
    policies = list(session.scalars(query))
    if status is None:
        return policies
    matched = []
    for policy in policies:
        versions = session.scalars(select(PolicyVersion.status).where(PolicyVersion.policy_id == policy.policy_id))
        if status in set(versions):
            matched.append(policy)
    return matched


def get_policy(session: Session, principal: Principal, policy_id: str) -> tuple[Policy, list[PolicyVersion]]:
    policy = _readable_policy(session, principal, policy_id)
    versions = list(session.scalars(select(PolicyVersion).where(PolicyVersion.policy_id == policy.policy_id)
                                    .order_by(PolicyVersion.version)))
    return policy, versions


def _transition(session, principal, version_id, expected_revision, permission, source, target, action, **fields):
    policy, version = get_version(session, principal, version_id)
    _require(principal, permission, policy.team_id)
    _expect(version, expected_revision)
    if version.status != source:
        raise InvalidTransition(f"cannot {action} from {version.status}")
    version.status = target
    version.revision += 1
    for name, value in fields.items():
        setattr(version, name, value)
    _audit(session, principal, action, "policy_version", version.version_id, policy.team_id,
           rule_key=policy.rule_key, version=version.version, from_status=source, to_status=target)
    session.flush()
    return policy, version


def submit_version(session, principal, version_id: str, expected_revision: int):
    return _transition(
        session, principal, version_id, expected_revision, Permission.POLICY_WRITE, "draft", "in_review",
        "policy.version.submit", submitted_by=principal.user_id, submitted_at=datetime.now(timezone.utc),
    )


def reject_version(session, principal, version_id: str, expected_revision: int, review_note: str):
    return _transition(
        session, principal, version_id, expected_revision, Permission.POLICY_APPROVE, "in_review", "draft",
        "policy.version.reject", review_note=review_note,
    )


def approve_version(session, principal, version_id: str, expected_revision: int, legal_review_reference: str):
    policy, version = get_version(session, principal, version_id)
    _require(principal, Permission.POLICY_APPROVE, policy.team_id)
    _expect(version, expected_revision)
    if version.status != "in_review":
        raise InvalidTransition("cannot approve from this status")
    if principal.user_id in {version.author_user_id, version.submitted_by}:
        raise PolicyForbidden(Permission.POLICY_APPROVE)
    if not legal_review_reference or not legal_review_reference.strip():
        raise InvalidTransition("legal review reference is required")
    version.status = "approved"
    version.revision += 1
    version.approved_by = principal.user_id
    version.approved_at = datetime.now(timezone.utc)
    version.legal_review_reference = legal_review_reference
    _audit(session, principal, "policy.version.approve", "policy_version", version.version_id, policy.team_id,
           rule_key=policy.rule_key, version=version.version, from_status="in_review", to_status="approved")
    session.flush()
    return policy, version


def revoke_version(session, principal, version_id: str, expected_revision: int, revocation_reason: str):
    return _transition(
        session, principal, version_id, expected_revision, Permission.POLICY_APPROVE, "approved", "revoked",
        "policy.version.revoke", revoked_by=principal.user_id, revoked_at=datetime.now(timezone.utc),
        revocation_reason=revocation_reason,
    )


__all_errors__ = (PolicyCatalogError, PolicyConflictError)
