"""Finite-horizon CP-SAT planner for PRD v4.2, with explicit unknowns.

Hours are integer *effective* hours in a known, disjoint time bucket. Capacity
may cover several skills but can never be used twice. New hires only appear
after recruitment/admission/training; mentoring consumes existing capacity.

This model is NOT a legal-validator or an employee roster. Its callers must
provide independently approved policy evidence, schedules and role costs.
"""
from dataclasses import dataclass
from datetime import date, timedelta
from math import isfinite
from typing import Literal

from ortools import __version__
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
    caps_by_window: dict[tuple[date, date], int] | None = None
    flexible_caps_by_window: dict[tuple[date, date], int] | None = None
    flexible_intervals: tuple[str, ...] = ()


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
    ends_before: date | None = None
    weekly_ramp_percent: tuple[int, ...] = ()

    def effective_hours(self, start: date, end: date) -> int:
        if start < self.ready_on or (self.ends_before is not None and end > self.ends_before):
            return 0
        lead = (start - self.ready_on) // timedelta(weeks=1)
        schedule = self.weekly_ramp_percent
        percent = schedule[min(lead, len(schedule) - 1)] if schedule else self.ramp_percent
        return self.hours_per_person * percent // 100


@dataclass(frozen=True)
class CpSatPlan:
    status: Literal["optimal", "feasible", "infeasible", "unknown", "blocked"]
    hires: dict[str, int]
    pool_allocations: dict[str, dict[str, int]]
    hire_allocations: dict[str, dict[str, int]]
    operational_residual: dict[str, int]
    total_hiring_cost_cents: int | None
    limitations: tuple[str, ...]
    solver_version: str = __version__


def solve_capacity(
    *, needs: list[IntervalDemand], pools: list[ExistingPool], options: list[HiringOption],
    budget_cents: int | None, policy_evidence_id: str | None, policy_verified: bool,
    timeout_seconds: float = 5.0, simulation_only: bool = False,
    existing_interval_caps: dict[str, int] | None = None,
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
    if budget_cents < 0 or not isfinite(timeout_seconds) or not 0 < timeout_seconds <= 30:
        return blocked("INVALID_BUDGET_OR_TIMEOUT")
    if any(
        n.start >= n.end_exclusive or n.mandatory_hours < 0 or
        n.target_hours < n.mandatory_hours for n in needs
    ):
        return blocked("INVALID_DEMAND")
    if any(p.total_hours < 0 or not p.schedule_verified
           or any(v < 0 for caps in (p.caps_by_interval, p.caps_by_window, p.flexible_caps_by_window)
                  for v in (caps or {}).values()) for p in pools):
        return blocked("POOL_RIGHTS_UNVERIFIED")
    if any(o.max_people < 0 or o.hours_per_person < 0 or o.cost_cents < 0
           or o.mentor_hours_per_hire < 0 or not 0 <= o.ramp_percent <= 100
           or any(not 0 <= r <= 100 for r in o.weekly_ramp_percent)
           or (o.ends_before is not None and o.ends_before <= o.ready_on)
           or not o.modality_verified for o in options):
        return blocked("HIRING_RIGHTS_UNVERIFIED")
    pool_by_id = {p.pool_id: p for p in pools}
    if any(o.mentor_hours_per_hire and o.mentor_pool_id not in pool_by_id for o in options):
        return blocked("MENTOR_POOL_UNKNOWN")

    # Identical windows share capacity. Partially overlapping windows do not
    # have a valid common period budget and require a different interval grid.
    windows = {need.interval_id: (need.start, need.end_exclusive) for need in needs}
    distinct_windows = sorted(set(windows.values()))
    if any(first[1] > second[0] for first, second in zip(distinct_windows, distinct_windows[1:])):
        return blocked("OVERLAPPING_INTERVAL_GRID")
    same_window = {}
    for interval_id, window in windows.items():
        same_window.setdefault(window, []).append(interval_id)

    if existing_interval_caps and any(key not in windows or cap < 0 for key, cap in existing_interval_caps.items()):
        return blocked("INVALID_EXISTING_INTERVAL_LIMIT")
    objective_scale = sum(o.cost_cents * o.max_people for o in options) + 1
    if objective_scale * (sum(n.target_hours for n in needs) + 1) >= 2 ** 62:
        return blocked("MODEL_LIMIT_EXCEEDED")

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
        if existing_interval_caps is not None and need.interval_id in existing_interval_caps:
            model.add(sum(assignments) <= existing_interval_caps[need.interval_id])
        for option in options:
            effective = option.effective_hours(need.start, need.end_exclusive)
            if effective and need.skill in option.eligible_skills and need.shift in option.eligible_shifts:
                var = model.new_int_var(0, option.max_people * effective,
                                        "role_" + option.role_id + "_" + need.interval_id)
                model.add(var <= effective * hires[option.role_id])
                hired[(option.role_id, need.interval_id)] = var
                assignments.append(var)
        cover = sum(assignments)
        model.add_linear_constraint(cover, need.mandatory_hours, need.target_hours)
        residual = model.new_int_var(0, need.target_hours, "deficit_" + need.interval_id)
        model.add(residual == need.target_hours - cover)
        deficit[need.interval_id] = residual

    for pool in pools:
        used = [v for (pid, _), v in existing.items() if pid == pool.pool_id]
        mentor_demand = sum(
            o.mentor_hours_per_hire * hires[o.role_id]
            for o in options if o.mentor_pool_id == pool.pool_id
        )
        model.add(sum(used) + mentor_demand <= pool.total_hours)
        for window, group in same_window.items():
            weekly_cap = (pool.caps_by_window.get(window, 0) if pool.caps_by_window is not None
                          else max((pool.caps_by_interval.get(key, 0) for key in group), default=0))
            mentoring = sum(
                o.mentor_hours_per_hire * hires[o.role_id]
                for o in options if o.mentor_pool_id == pool.pool_id
                and window[0] < o.ready_on <= window[1]
            )
            model.add(sum(existing[(pool.pool_id, key)] for key in group
                          if (pool.pool_id, key) in existing) + mentoring <= weekly_cap)
            if pool.flexible_caps_by_window is not None:
                model.add(sum(existing[(pool.pool_id, key)] for key in group
                              if (pool.pool_id, key) in existing and key in pool.flexible_intervals)
                          <= pool.flexible_caps_by_window.get(window, 0))

    for option in options:
        for window, group in same_window.items():
            model.add(sum(hired[(option.role_id, key)] for key in group
                          if (option.role_id, key) in hired)
                      <= hires[option.role_id] * option.effective_hours(*window))

    total_cost = sum(o.cost_cents * hires[o.role_id] for o in options)
    model.add(total_cost <= budget_cents)
    model.minimize(objective_scale * sum(deficit.values()) + total_cost)

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
