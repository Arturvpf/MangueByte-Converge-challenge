"""Policy identity and immutable versions (P2-02).

Approved content is never updated or deleted. A change is a new version.
NULL team_id or employee_category means "every team" or "every category";
the database UNIQUE does not treat those NULLs as equal, so before_flush does.
"""
from datetime import date, datetime, timezone
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import (
    JSON, CheckConstraint, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, event, inspect, select,
)
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, Session, mapped_column

from backend.app.core.database import Base
from backend.app.policies.catalog import UnknownRuleKey, category_for, validate_parameters
from backend.app.policies.schemas import (
    CATEGORY_MAX, EMPLOYEE_CATEGORY_MAX, ID_MAX, LEGAL_REVIEW_MAX, REVIEW_NOTE_MAX,
    REVOCATION_REASON_MAX, RULE_KEY_MAX, SOURCE_REFERENCE_MAX, TEAM_ID_MAX, TITLE_MAX,
)

# politica_interna is 17 characters, so this is wider than a 16-character column.
SOURCE_KIND_MAX = 32
CONTENT_FIELDS = frozenset({
    "parameters", "source_kind", "source_reference", "valid_from", "valid_until", "content_hash",
})
IDENTITY_FIELDS = frozenset({"tenant_id", "rule_key", "category", "team_id", "employee_category"})


class PolicyImmutableError(RuntimeError):
    pass


class PolicyConflictError(RuntimeError):
    pass


class PolicyCatalogError(ValueError):
    pass


def _utcnow():
    return datetime.now(timezone.utc)


class Policy(Base):
    __tablename__ = "policies"
    __table_args__ = (
        UniqueConstraint("tenant_id", "rule_key", "team_id", "employee_category", name="uq_policies_scope"),
    )
    policy_id: Mapped[str] = mapped_column(String(ID_MAX), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(TEAM_ID_MAX), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    rule_key: Mapped[str] = mapped_column(String(RULE_KEY_MAX), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(CATEGORY_MAX), nullable=False)
    team_id: Mapped[str | None] = mapped_column(String(TEAM_ID_MAX), nullable=True, index=True)
    employee_category: Mapped[str | None] = mapped_column(String(EMPLOYEE_CATEGORY_MAX), nullable=True)
    title: Mapped[str] = mapped_column(String(TITLE_MAX), nullable=False)
    created_by: Mapped[str] = mapped_column(String(ID_MAX), ForeignKey("users.user_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)


class PolicyVersion(Base):
    __tablename__ = "policy_versions"
    __table_args__ = (
        UniqueConstraint("policy_id", "version", name="uq_policy_versions_number"),
        UniqueConstraint("policy_id", "idempotency_key", name="uq_policy_versions_idempotency"),
        CheckConstraint("status IN ('draft', 'in_review', 'approved', 'revoked')", name="ck_policy_versions_status"),
        CheckConstraint("version > 0", name="ck_policy_versions_version"),
        CheckConstraint("revision >= 0", name="ck_policy_versions_revision"),
        CheckConstraint("valid_until IS NULL OR valid_until > valid_from", name="ck_policy_versions_validity"),
        CheckConstraint(
            "source_kind IN ('lei', 'emenda', 'cct', 'act', 'politica_interna', 'sintetico')",
            name="ck_policy_versions_source_kind",
        ),
        CheckConstraint("length(content_hash) = 64", name="ck_policy_versions_hash"),
    )
    version_id: Mapped[str] = mapped_column(String(ID_MAX), primary_key=True, default=lambda: str(uuid4()))
    policy_id: Mapped[str] = mapped_column(String(ID_MAX), ForeignKey("policies.policy_id"), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(TEAM_ID_MAX), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    parameters: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(SOURCE_KIND_MAX), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(SOURCE_REFERENCE_MAX), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    author_user_id: Mapped[str] = mapped_column(String(ID_MAX), ForeignKey("users.user_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    submitted_by: Mapped[str | None] = mapped_column(String(ID_MAX), ForeignKey("users.user_id"), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(ID_MAX), ForeignKey("users.user_id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    legal_review_reference: Mapped[str | None] = mapped_column(String(LEGAL_REVIEW_MAX), nullable=True)
    review_note: Mapped[str | None] = mapped_column(String(REVIEW_NOTE_MAX), nullable=True)
    revoked_by: Mapped[str | None] = mapped_column(String(ID_MAX), ForeignKey("users.user_id"), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(String(REVOCATION_REASON_MAX), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)


def _changed(obj, name: str) -> bool:
    return inspect(obj).attrs[name].history.has_changes()


def _scope_key(policy: Policy):
    return (policy.tenant_id, policy.rule_key, policy.team_id, policy.employee_category)


def _policy_for(session: Session, policy_id: str) -> Policy | None:
    for obj in session.new:
        if isinstance(obj, Policy) and obj.policy_id == policy_id:
            return obj
    with session.no_autoflush:
        return session.get(Policy, policy_id)


def _check_catalog(session: Session, policy: Policy) -> None:
    if policy.team_id is not None and policy.team_id != policy.team_id.strip():
        raise PolicyCatalogError("invalid team_id")
    if policy.employee_category is not None and policy.employee_category != policy.employee_category.strip():
        raise PolicyCatalogError("invalid employee_category")
    try:
        expected = category_for(policy.rule_key)
    except UnknownRuleKey as exc:
        raise PolicyCatalogError(str(exc)) from exc
    if policy.category != expected:
        raise PolicyCatalogError("category does not match rule_key")


def _check_parameters(session: Session, version: PolicyVersion) -> None:
    policy = _policy_for(session, version.policy_id)
    if policy is None:
        raise PolicyCatalogError("version requires its policy")
    try:
        validate_parameters(policy.rule_key, version.parameters)
    except (UnknownRuleKey, ValidationError) as exc:
        raise PolicyCatalogError(str(exc)) from exc


def _duplicate_scope(session: Session, policies: list[Policy]) -> None:
    for index, policy in enumerate(policies):
        if any(_scope_key(policy) == _scope_key(other) for other in policies[index + 1:]):
            raise PolicyConflictError("duplicate policy scope")
        clauses = [
            Policy.tenant_id == policy.tenant_id,
            Policy.rule_key == policy.rule_key,
            Policy.policy_id != policy.policy_id,
            Policy.team_id.is_(None) if policy.team_id is None else Policy.team_id == policy.team_id,
            Policy.employee_category.is_(None) if policy.employee_category is None else Policy.employee_category == policy.employee_category,
        ]
        with session.no_autoflush:
            if session.scalar(select(Policy.policy_id).where(*clauses).limit(1)) is not None:
                raise PolicyConflictError("duplicate policy scope")


def _is_policy_dml(state) -> bool:
    table = getattr(state.statement, "table", None)
    name = getattr(table, "name", None)
    if name in {Policy.__tablename__, PolicyVersion.__tablename__}:
        return True
    return any(mapper.class_ in {Policy, PolicyVersion} for mapper in state.all_mappers)


@event.listens_for(Session, "before_flush")
def _guard_policies(session, flush_context, instances):
    for obj in session.deleted:
        if isinstance(obj, (Policy, PolicyVersion)):
            raise PolicyImmutableError("policies and versions are not deleted")
    for obj in session.dirty:
        if isinstance(obj, PolicyVersion) and session.is_modified(obj):
            history = inspect(obj).attrs.status.history
            previous = history.deleted[0] if history.deleted else obj.status
            if previous != "draft" and any(_changed(obj, name) for name in CONTENT_FIELDS):
                raise PolicyImmutableError("version content is immutable after draft")
        if isinstance(obj, Policy) and any(_changed(obj, name) for name in IDENTITY_FIELDS):
            raise PolicyImmutableError("policy identity is stable")
    policies = [obj for obj in list(session.new) + list(session.dirty) if isinstance(obj, Policy)]
    for policy in policies:
        _check_catalog(session, policy)
    _duplicate_scope(session, policies)
    for obj in list(session.new) + list(session.dirty):
        if isinstance(obj, PolicyVersion) and (obj in session.new or _changed(obj, "parameters")):
            _check_parameters(session, obj)


@event.listens_for(Session, "do_orm_execute")
def _block_policy_bulk(state):
    if (state.is_update or state.is_delete) and _is_policy_dml(state):
        raise PolicyImmutableError("policies and versions are not deleted or bulk-updated")
