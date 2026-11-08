"""Finite-horizon CP-SAT planner for PRD v4.2, with explicit unknowns.

Hours are integer *effective* hours in a known, disjoint time bucket. Capacity
may cover several skills but can never be used twice. New hires only appear
after recruitment/admission/training; mentoring consumes existing capacity.

This model is NOT a legal-validator or an employee roster. Its callers must
provide independently approved policy evidence, schedules and role costs.
"""
from dataclasses import dataclass
from datetime import date
from typing import Literal

from ortools.sat.python import cp_model


@dataclass(frozen=True)
class IntervalDemand:
    interval_id: str
    start: date
    end_exclusive: date
    skill: str
    shift: str
    mandatory_hours: int
    target_hours: int


@dataclass(frozen=True)
class ExistingPool:
    pool_id: str
    eligible_skills: tuple[str, ...]
    eligible_shifts: tuple[str, ...]
    total_hours: int
    caps_by_interval: dict[str, int]
    qualified: bool = True
    schedule_verified: bool = False


@dataclass(frozen=True)
class HiringOption:
    role_id: str
    eligible_skills: tuple[str, ...]
    eligible_shifts: tuple[str, ...]
    ready_on: date
    hours_per_person: int
    max_people: int
    cost_cents: int
    ramp_percent: int
    mentor_pool_id: str | None = None
    mentor_hours_per_hire: int = 0
    modality_verified: bool = False


@dataclass(frozen=True)
class CpSatPlan:
    status: Literal["optimal", "feasible", "infeasible", "unknown", "blocked"]
    hires: dict[str, int]
    pool_allocations: dict[str, dict[str, int]]
    hire_allocations: dict[str, dict[str, int]]
    operational_residual: dict[str, int]
    total_hiring_cost_cents: int | None
    limitations: tuple[str, ...]


def solve_capacity(
    *, needs: list[IntervalDemand], pools: list[ExistingPool], options: list[HiringOption],
    budget_cents: int | None, policy_evidence_id: str | None, policy_verified: bool,
    timeout_seconds: float = 5.0, simulation_only: bool = False,
) -> CpSatPlan:
    def blocked(reason):
        return CpSatPlan("blocked", {}, {}, {}, {}, None, (reason,))

    # Mathematical what-if exploration can use *unverified* inputs, but
    # the returned plan must be permanently labelled as non-approvable.
    # The independent validator never consumes this flag as legal evidence.
    if (not policy_evidence_id or not policy_verified) and not simulation_only:
        return blocked("POLICY_REVIEW_REQUIRED")
    if budget_cents is None:
        return blocked("BUDGET_UNKNOWN")
    if (not needs or len({n.interval_id for n in needs}) != len(needs)
            or len({p.pool_id for p in pools}) != len(pools)
            or len({o.role_id for o in options}) != len(options)):
        return blocked("INVALID_IDENTIFIERS")
    if budget_cents < 0 or not 0 < timeout_seconds <= 30:
        return blocked("INVALID_BUDGET_OR_TIMEOUT")
    if any(
        n.start >= n.end_exclusive or n.mandatory_hours < 0 or
        n.target_hours < n.mandatory_hours for n in needs
    ):
        return blocked("INVALID_DEMAND")
    if any(p.total_hours < 0 or not p.schedule_verified
           or any(v < 0 for v in p.caps_by_interval.values()) for p in pools):
        return blocked("POOL_RIGHTS_UNVERIFIED")
    if any(o.max_people < 0 or o.hours_per_person < 0 or o.cost_cents < 0
           or o.mentor_hours_per_hire < 0 or not 0 <= o.ramp_percent <= 100
           or not o.modality_verified for o in options):
        return blocked("HIRING_RIGHTS_UNVERIFIED")
    pool_by_id = {p.pool_id: p for p in pools}
    if any(o.mentor_hours_per_hire and o.mentor_pool_id not in pool_by_id for o in options):
        return blocked("MENTOR_POOL_UNKNOWN")

    # Identical time windows can share different skills. Partially overlapping
    # intervals are rejected instead of pretending they are independent hours.
    windows = {}
    for need in needs:
        key = (need.start, need.end_exclusive)
        if need.interval_id in windows:
            return blocked("DUPLICATE_WINDOW_ID")
        windows[need.interval_id] = key
    pairs = list(windows.items())
    for index, (first_id, (first_start, first_end)) in enumerate(pairs):
        for second_id, (second_start, second_end) in pairs[index + 1:]:
            if first_start < second_end and second_start < first_end:
                if first_start != second_start or first_end != second_end:
                    return blocked("OVERLAPPING_INTERVAL_GRID")
    same_window = {}
    for interval_id, window in windows.items():
        same_window.setdefault(window, []).append(interval_id)

    model = cp_model.CpModel()
    existing = {}
    hired = {}
    hires = {}
    deficit = {}
    for option in options:
        hires[option.role_id] = model.new_int_var(0, option.max_people, "hire_" + option.role_id)

    for need in needs:
        assignments = []
        for pool in pools:
            cap = pool.caps_by_interval.get(need.interval_id, 0)
            if (cap and pool.qualified and need.skill in pool.eligible_skills
                    and need.shift in pool.eligible_shifts):
                var = model.new_int_var(0, min(cap, pool.total_hours),
                                        "pool_" + pool.pool_id + "_" + need.interval_id)
                existing[(pool.pool_id, need.interval_id)] = var
                assignments.append(var)
        for option in options:
            if (need.start >= option.ready_on and need.skill in option.eligible_skills
                    and need.shift in option.eligible_shifts):
                effective = option.hours_per_person * option.ramp_percent // 100
                var = model.new_int_var(0, option.max_people * effective,
                                        "role_" + option.role_id + "_" + need.interval_id)
                model.add(var <= effective * hires[option.role_id])
                hired[(option.role_id, need.interval_id)] = var
                assignments.append(var)
        cover = sum(assignments)
        model.add(cover >= need.mandatory_hours)
        residual = model.new_int_var(0, need.target_hours, "deficit_" + need.interval_id)
        model.add(residual >= need.target_hours - cover)
        deficit[need.interval_id] = residual

    for pool in pools:
        used = [v for (pid, _), v in existing.items() if pid == pool.pool_id]
        mentor_demand = sum(
            o.mentor_hours_per_hire * hires[o.role_id]
            for o in options if o.mentor_pool_id == pool.pool_id
        )
        model.add(sum(used) + mentor_demand <= pool.total_hours)
        for group in same_window.values():
            model.add(sum(existing[(pool.pool_id, k)] for k in group
                          if (pool.pool_id, k) in existing) <=
                      max((pool.caps_by_interval.get(k, 0) for k in group), default=0))

    for option in options:
        # HiringOption.hours_per_person is capacity PER time window, not across
        # the whole multi-week horizon. Counting it once globally incorrectly
        # makes a person unavailable after their first week.
        effective = option.hours_per_person * option.ramp_percent // 100
        # No cross-skill double counting within any shared time window.
        for group in same_window.values():
            model.add(sum(hired[(option.role_id, k)] for k in group
                          if (option.role_id, k) in hired) <=
                      hires[option.role_id] * effective)

    total_cost = sum(o.cost_cents * hires[o.role_id] for o in options)
    model.add(total_cost <= budget_cents)
    max_possible_cost = sum(o.cost_cents * o.max_people for o in options)
    model.minimize((max_possible_cost + 1) * sum(deficit.values()) + total_cost)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = timeout_seconds
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 42
    status = solver.solve(model)
    if status == cp_model.INFEASIBLE:
        return CpSatPlan("infeasible", {}, {}, {}, {}, None,
                         ("Cobertura mínima, qualificações, lead time ou orçamento incompatíveis.",))
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return CpSatPlan("unknown", {}, {}, {}, {}, None, ("Limite de tempo ou busca sem solução.",))
    return CpSatPlan(
        "optimal" if status == cp_model.OPTIMAL else "feasible",
        {key: solver.value(variable) for key, variable in hires.items()},
        {pool.pool_id: {n.interval_id: solver.value(existing[(pool.pool_id, n.interval_id)])
                        for n in needs if (pool.pool_id, n.interval_id) in existing}
         for pool in pools},
        {option.role_id: {n.interval_id: solver.value(hired[(option.role_id, n.interval_id)])
                          for n in needs if (option.role_id, n.interval_id) in hired}
         for option in options},
        {key: solver.value(variable) for key, variable in deficit.items()},
        solver.value(total_cost),
        (("SIMULACAO_EXPLORATORIA_SEM_VALIDACAO_JURIDICA_OU_ESCALA",)
         if simulation_only else ())
        + ("Resultado restrito às regras, custos e intervalos explicitamente modelados.",),
    )
