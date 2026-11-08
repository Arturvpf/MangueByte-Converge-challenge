"""Coverage solver: one hour, one use; statuses stay distinct."""
from datetime import date
from decimal import Decimal

from backend.app.contracts.v1 import Period
from backend.app.metrics.engine import Allocation as MetricAllocation
from backend.app.metrics.engine import Matrix, Pool, Row as MetricRow, validate_allocations
from backend.app.optimization.solver import Row, solve


def test_optimal_residual_and_single_use_of_each_hour():
    result = solve(
        {"pool": 10},
        [Row("a", "day", ("pool",), 10), Row("b", "day", ("pool",), 10)],
        {"a": 10, "b": 10},
    )
    assert result.status == "optimal"
    assert sum(item.hours for item in result.allocations) == 10
    assert sum(result.residual_hours.values()) == 10
    period = Period(start=date(2026, 11, 2), end_exclusive=date(2026, 11, 9), timezone="America/Fortaleza")
    matrix = Matrix(
        "tenant", "team", "snap", period, "hours_per_period",
        (Pool("pool", Decimal(10)),),
        (MetricRow("a", "day", ("pool",), Decimal(10), None), MetricRow("b", "day", ("pool",), Decimal(10), None)),
        (("a", Decimal(10)), ("b", Decimal(10))), (),
    )
    validate_allocations(matrix, [
        MetricAllocation(item.pool_id, item.skill_id, item.shift_id, Decimal(item.hours)) for item in result.allocations
    ])


def test_infeasible_minimum_is_not_a_timeout():
    result = solve({"pool": 5}, [Row("a", "day", ("pool",), 8, minimum=8)], {"a": 8})
    assert result.status == "infeasible" and result.allocations == ()
    capped = solve({"pool": 20}, [Row("a", "day", ("pool",), 20, minimum=8)], {"a": 8}, max_total_hours=4)
    assert capped.status == "infeasible"


def test_timeout_without_a_solution_is_unknown():
    result = solve(
        {"a": 1, "b": 1},
        [Row("skill", "day", ("a", "b"), 2)],
        {"skill": 2},
        max_expansions=0,
    )
    assert result.status == "unknown" and result.allocations == ()
    assert "inviabilidade" in result.limitations[0]


def test_partial_search_is_feasible_not_infeasible():
    result = solve(
        {"a": 1, "b": 1},
        [Row("skill", "day", ("a", "b"), 2)],
        {"skill": 2},
        max_expansions=1,
    )
    assert result.status == "feasible"
    assert sum(item.hours for item in result.allocations) == 1
    assert result.residual_hours["skill"] == 1
