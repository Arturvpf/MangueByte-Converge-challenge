"""Small deterministic CP-SAT acceptance cases for mandatory vs operational coverage."""
from datetime import date

from backend.app.optimization.cpsat_v42 import (
    ExistingPool, HiringOption, IntervalDemand, solve_capacity,
)

D0 = date(2026, 11, 9)
D1 = date(2026, 11, 16)


def need(mandatory=3, target=5):
    return IntervalDemand("day-helpdesk", D0, D1, "helpdesk", "day", mandatory, target)


def pool(hours=3):
    return ExistingPool("current", ("helpdesk",), ("day",), hours, {"day-helpdesk": hours},
                        qualified=True, schedule_verified=True)


def hire(ready=D0, mentor=0):
    return HiringOption("helpdesk-jr", ("helpdesk",), ("day",), ready, 2, 2,
                        50000, 100, mentor_pool_id="current" if mentor else None,
                        mentor_hours_per_hire=mentor, modality_verified=True)


def solve(**overrides):
    options = dict(needs=[need()], pools=[pool()], options=[hire()],
                   budget_cents=120000, policy_evidence_id="policy-1", policy_verified=True)
    options.update(overrides)
    return solve_capacity(**options)


def test_hire_must_be_ready_before_peak_and_budget_authorized():
    result = solve()
    assert result.status == "optimal"
    assert result.hires["helpdesk-jr"] == 1
    assert result.operational_residual["day-helpdesk"] == 0
    assert result.total_hiring_cost_cents == 50000
    late = solve(options=[hire(ready=D1)], needs=[need(mandatory=5, target=5)])
    assert late.status == "infeasible"
    assert solve(budget_cents=None).status == "blocked"


def test_operational_target_can_remain_short_if_mandatory_is_met():
    result = solve(options=[], budget_cents=0)
    assert result.status == "optimal"
    assert result.operational_residual["day-helpdesk"] == 2


def test_mentor_consumes_real_hours_and_may_make_plan_infeasible():
    blocked = solve(needs=[need(mandatory=5, target=5)], options=[hire(mentor=2)])
    assert blocked.status == "infeasible"


def test_shared_pool_hours_and_qualifications_are_not_double_counted():
    two = [
        IntervalDemand("a", D0, D1, "helpdesk", "day", 2, 2),
        IntervalDemand("b", D0, D1, "billing", "day", 2, 2),
    ]
    shared = ExistingPool("staff", ("helpdesk", "billing"), ("day",), 3,
                          {"a": 3, "b": 3}, qualified=True, schedule_verified=True)
    result = solve(needs=two, pools=[shared], options=[], budget_cents=0)
    assert result.status == "infeasible"
    disallowed = solve(needs=[need()], pools=[pool()],
                       options=[hire()], policy_verified=False)
    assert disallowed.status == "blocked"


def test_one_hire_provides_capacity_in_each_separate_week():
    from datetime import timedelta
    next_week = D1 + timedelta(days=7)
    needs = [
        IntervalDemand("week-1", D0, D1, "helpdesk", "day", 2, 2),
        IntervalDemand("week-2", D1, next_week, "helpdesk", "day", 2, 2),
    ]
    option = HiringOption("role", ("helpdesk",), ("day",), D0, 2, 1, 100, 100,
                          modality_verified=True)
    result = solve_capacity(
        needs=needs, pools=[], options=[option], budget_cents=100,
        policy_evidence_id="approved-test", policy_verified=True,
    )
    assert result.status == "optimal"
    assert result.hires == {"role": 1}
    assert result.operational_residual == {"week-1": 0, "week-2": 0}
    assert result.hire_allocations["role"] == {"week-1": 2, "week-2": 2}
