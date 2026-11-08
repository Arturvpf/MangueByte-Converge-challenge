"""Deterministic rule resolution. No default limits."""
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.policies.catalog import validate_parameters
from backend.app.policies.models import Policy, PolicyVersion
from backend.app.policies.schemas import PolicyResolution, ResolvedRule
from backend.app.policies.service import content_hash


def _level(policy: Policy) -> int:
    return (policy.team_id is not None) * 2 + (policy.employee_category is not None)


def _covers(policy: Policy, team_id: str, employee_category: str | None) -> bool:
    team_ok = policy.team_id is None or policy.team_id == team_id
    category_ok = policy.employee_category is None or policy.employee_category == employee_category
    return team_ok and category_ok


def _in_force(version: PolicyVersion, on_date: date) -> bool:
    if version.status != "approved" or version.valid_from > on_date:
        return False
    return version.valid_until is None or on_date < version.valid_until


def _hash_ok(version: PolicyVersion) -> bool:
    return version.content_hash == content_hash(
        parameters=version.parameters, source_kind=version.source_kind, source_reference=version.source_reference,
        valid_from=version.valid_from, valid_until=version.valid_until,
    )


def _review(rule_key, reason: str) -> dict:
    return {
        "rule_key": rule_key, "status": "review_required", "version_id": None, "version": None,
        "parameters": None, "source_reference": None, "valid_from": None, "valid_until": None, "reason": reason,
    }


def _resolved(policy: Policy, version: PolicyVersion) -> dict:
    return {
        "rule_key": policy.rule_key, "status": "resolved", "version_id": version.version_id, "version": version.version,
        "parameters": validate_parameters(policy.rule_key, version.parameters),
        "source_reference": version.source_reference, "valid_from": version.valid_from,
        "valid_until": version.valid_until, "reason": None,
    }


def _finish(tenant_id: str, team_id: str, data_snapshot_id: str, on_date: date, items: list[dict]) -> PolicyResolution:
    payload = [ResolvedRule.model_validate(item) for item in items]
    return PolicyResolution.model_validate({
        "schema_version": "1.0", "tenant_id": tenant_id, "team_id": team_id,
        "data_snapshot_id": data_snapshot_id, "on_date": on_date, "items": payload,
        "complete": all(item.status == "resolved" for item in payload),
    })


def resolve(session: Session, *, tenant_id: str, team_id: str, employee_category: str | None, on_date: date,
            rule_keys: list[str], data_snapshot_id: str) -> PolicyResolution:
    items = []
    for rule_key in rule_keys:
        rows = session.execute(select(PolicyVersion, Policy).join(Policy, Policy.policy_id == PolicyVersion.policy_id).where(
            Policy.tenant_id == tenant_id, PolicyVersion.tenant_id == tenant_id, Policy.rule_key == rule_key,
        )).all()
        candidates = [(version, policy) for version, policy in rows
                      if _covers(policy, team_id, employee_category) and _in_force(version, on_date)]
        if not candidates:
            items.append(_review(rule_key, "missing"))
            continue
        best = max(_level(policy) for _, policy in candidates)
        chosen = sorted(((version, policy) for version, policy in candidates if _level(policy) == best),
                        key=lambda pair: pair[0].version_id)
        if len(chosen) != 1:
            items.append(_review(rule_key, "conflict"))
            continue
        version, policy = chosen[0]
        items.append(_resolved(policy, version) if _hash_ok(version) else _review(rule_key, "hash_mismatch"))
    return _finish(tenant_id, team_id, data_snapshot_id, on_date, items)


def resolve_pinned(session: Session, *, tenant_id: str, team_id: str, on_date: date, version_ids: list[str],
                   data_snapshot_id: str) -> PolicyResolution:
    items = []
    for version_id in version_ids:
        row = session.execute(select(PolicyVersion, Policy).join(Policy, Policy.policy_id == PolicyVersion.policy_id).where(
            PolicyVersion.version_id == version_id, PolicyVersion.tenant_id == tenant_id, Policy.tenant_id == tenant_id,
        )).first()
        if row is None:
            items.append({
                "rule_key": None, "status": "review_required", "version_id": version_id, "version": None,
                "parameters": None, "source_reference": None, "valid_from": None, "valid_until": None,
                "reason": "pinned_not_found",
            })
            continue
        version, policy = row
        if version.status == "revoked":
            items.append({
                "rule_key": policy.rule_key, "status": "review_required", "version_id": version.version_id,
                "version": version.version, "parameters": None, "source_reference": None, "valid_from": None,
                "valid_until": None, "reason": "pinned_revoked",
            })
            continue
        if version.status != "approved" or not _hash_ok(version):
            items.append(_review(policy.rule_key, "hash_mismatch" if version.status == "approved" else "conflict"))
            continue
        items.append(_resolved(policy, version))
    return _finish(tenant_id, team_id, data_snapshot_id, on_date, items)
