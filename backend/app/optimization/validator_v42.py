"""Independent, fail-closed validation of one interval of a v4.2 plan.

This module does not interpret legislation or trust a language model's
`conclusive` assertion. It checks physical coverage and only accepts explicit
evidence from the upstream, authorized policy/budget validators.
"""
from collections import defaultdict

from backend.app.contracts.v42 import (
    Assignment, CoverageNeed, PlanVerification, ReadyCapacity, ScenarioReadiness,
)


def verify_interval(
    *, scenario_id: str, need: CoverageNeed,
    capacity: list[ReadyCapacity], assignments: list[Assignment],
    readiness: ScenarioReadiness,
) -> PlanVerification:
    violations: list[str] = []
    limitations: list[str] = []
    if (not readiness.policy_rules_current or not readiness.policy_evidence_id
            or not readiness.rest_and_daily_limits_verified):
        violations.append("POLICY_REVIEW_REQUIRED")
    if not readiness.budget_approved:
        violations.append("BUDGET_NOT_APPROVED")
    if not readiness.legal_modality_verified:
        violations.append("MODALITY_REVIEW_REQUIRED")

    by_pool = {pool.pool_id: pool for pool in capacity}
    if len(by_pool) != len(capacity):
        violations.append("DUPLICATE_POOL")
    used = defaultdict(int)
    covered = 0
    for assignment in assignments:
        pool = by_pool.get(assignment.pool_id)
        if pool is None:
            violations.append("UNKNOWN_POOL")
            continue
        used[assignment.pool_id] += assignment.hours
        if (assignment.skill_id != need.skill_id or assignment.shift_id != need.shift_id
                or pool.skill_id != need.skill_id or pool.shift_id != need.shift_id):
            violations.append("SKILL_OR_SHIFT_MISMATCH")
            continue
        if not pool.qualification_verified:
            violations.append("TRAINING_NOT_COMPLETED")
            continue
        if not pool.approved_work_schedule:
            violations.append("SCHEDULE_NOT_APPROVED")
            continue
        if pool.ready_at > need.interval_start:
            violations.append("CAPACITY_ARRIVES_TOO_LATE")
            continue
        covered += assignment.hours
    for pool_id, hours in used.items():
        pool = by_pool.get(pool_id)
        if pool is not None and hours > pool.available_hours:
            violations.append("POOL_HOURS_EXCEEDED")
    mandatory_met = covered >= need.mandatory_hours
    if not mandatory_met:
        violations.append("MANDATORY_COVERAGE_MISSING")
    residual = max(need.target_hours - covered, 0)
    if residual:
        limitations.append("Operational target not fully covered; residual is not itself a hard-rule violation")
    violations = sorted(set(violations))
    return PlanVerification(
        scenario_id=scenario_id,
        status="blocked" if violations else "valid",
        mandatory_coverage_met=mandatory_met,
        operational_residual_hours=residual,
        violations=violations,
        limitations=limitations,
    )
