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

def verify_projection(needs, pools, options, interval_caps, plan):
    """Check allocation arithmetic independently of OR-Tools and block authorization."""
    violations = ["POLICY_REVIEW_REQUIRED", "BUDGET_NOT_APPROVED", "MODALITY_REVIEW_REQUIRED"]
    if plan.status not in {"optimal", "feasible"}:
        return {"status": "blocked", "mathematical_status": "unavailable",
                "mandatory_coverage_met": None, "violations": [*violations, "NO_SOLUTION_TO_VERIFY"]}
    windows = defaultdict(list)
    errors = set()
    for need in needs:
        windows[(need.start, need.end_exclusive)].append(need)
        existing = sum(hours.get(need.interval_id, 0) for hours in plan.pool_allocations.values())
        hired = sum(hours.get(need.interval_id, 0) for hours in plan.hire_allocations.values())
        covered = existing + hired
        if existing > interval_caps.get(need.interval_id, 0):
            errors.add("INTERVAL_EXISTING_CAP_EXCEEDED")
        if covered + plan.operational_residual.get(need.interval_id, -1) != need.target_hours:
            errors.add("COVERAGE_BALANCE_INVALID")
        if covered < need.mandatory_hours:
            errors.add("MANDATORY_COVERAGE_MISSING")
    for pool in pools:
        used = plan.pool_allocations.get(pool.pool_id, {})
        options_with_mentor = [option for option in options if option.mentor_pool_id == pool.pool_id]
        mentor_hours = sum(option.mentor_hours_per_hire * plan.hires[option.role_id]
                           for option in options_with_mentor)
        if sum(used.values()) + mentor_hours > pool.total_hours:
            errors.add("POOL_HORIZON_CAP_EXCEEDED")
        for window, group in windows.items():
            mentoring = sum(option.mentor_hours_per_hire * plan.hires[option.role_id]
                            for option in options_with_mentor if window[0] < option.ready_on <= window[1])
            if sum(used.get(n.interval_id, 0) for n in group) + mentoring > pool.caps_by_window[window]:
                errors.add("POOL_WEEKLY_CAP_EXCEEDED")
            moved = sum(used.get(n.interval_id, 0) for n in group if n.interval_id in pool.flexible_intervals)
            if moved > pool.flexible_caps_by_window[window]:
                errors.add("MOBILITY_CAP_EXCEEDED")
            for need in group:
                hours = used.get(need.interval_id, 0)
                if not 0 <= hours <= pool.caps_by_interval.get(need.interval_id, 0):
                    errors.add("POOL_ELIGIBILITY_EXCEEDED")
                if hours and (need.skill not in pool.eligible_skills or need.shift not in pool.eligible_shifts):
                    errors.add("SKILL_OR_SHIFT_MISMATCH")
    cost = 0
    for option in options:
        count = plan.hires.get(option.role_id, 0)
        cost += count * option.cost_cents
        if not 0 <= count <= option.max_people:
            errors.add("HEADCOUNT_LIMIT_EXCEEDED")
        allocation = plan.hire_allocations.get(option.role_id, {})
        for window, group in windows.items():
            if sum(allocation.get(n.interval_id, 0) for n in group) > count * option.effective_hours(*window):
                errors.add("HIRING_WINDOW_CAP_EXCEEDED")
            for need in group:
                if allocation.get(need.interval_id, 0) and (
                    need.skill not in option.eligible_skills or need.shift not in option.eligible_shifts
                ):
                    errors.add("HIRING_ELIGIBILITY_INVALID")
    if cost != plan.total_hiring_cost_cents:
        errors.add("HIRING_COST_MISMATCH")
    return {"status": "blocked", "mathematical_status": "invalid" if errors else "verified",
            "mandatory_coverage_met": (("MANDATORY_COVERAGE_MISSING" not in errors)
                                       if any(need.mandatory_hours for need in needs) else None),
            "violations": [*violations, *sorted(errors)]}
