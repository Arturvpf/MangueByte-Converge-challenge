"""Auditable, non-approvable quantitative what-if variants of five staffing strategies.

All outputs are *exploratory*, not certified schedules or employment advice.
Operational approval requires separate verified schedule, legal instrument, costs,
policy, independent validator, and version-matched human authorization.

Uses the same CP-SAT solver for A, B, C, D and E. The solver is never
represented as legally verified; skill/shift split from a weekly aggregate is
an explicit sensitivity assumption, NOT observed demand by shift.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, ROUND_CEILING

from backend.app.contracts.v1 import ForecastResult
from backend.app.data.schemas import SnapshotData
from backend.app.optimization.cpsat_v42 import (
    CpSatPlan, ExistingPool, HiringOption, IntervalDemand, solve_capacity,
)


@dataclass(frozen=True)
class WhatIf:
    kind: str
    summary: dict


def _ceil(number: Decimal) -> int:
    return int(number.to_integral_value(rounding=ROUND_CEILING))


def _week_needs(snapshot: SnapshotData, forecast: ForecastResult, cases_per_hour: Decimal,
                rework_fraction: Decimal):
    """Split each skill uniformly across its shifts; never pretend this is observed."""
    rows = snapshot.capacity.rows
    skills = {item.skill_id: Decimal(str(item.quantity))
              for item in snapshot.demand.records if item.quantity is not None}
    if not skills or not rows or not forecast.points or cases_per_hour <= 0:
        return []
    total = sum(skills.values())
    if total <= 0:
        return []
    needs = []
    for week_index, point in enumerate(forecast.points):
        if point.point_estimate is None:
            return []
        # Calibrated P50 if available; otherwise explicitly label point-baseline.
        cases = Decimal(str(point.p50 if point.p50 is not None else point.point_estimate))
        for skill in sorted(skills):
            shifts = sorted({row.shift_id for row in rows if row.skill_id == skill})
            if not shifts:
                return []
            hours = _ceil(cases * (1 + rework_fraction) * skills[skill] / total / cases_per_hour)
            # Keep the sum exact after integer rounding.
            normal, remainder = divmod(hours, len(shifts))
            for j, shift in enumerate(shifts):
                needed = normal + (1 if j < remainder else 0)
                needs.append(IntervalDemand(
                    interval_id=f"w{week_index+1}:{skill}:{shift}",
                    start=point.period.start, end_exclusive=point.period.end_exclusive,
                    skill=skill, shift=shift,
                    mandatory_hours=0,  # No verified mandatory-coverage matrix.
                    target_hours=needed,
                ))
    return needs


def _pools(snapshot: SnapshotData, needs: list[IntervalDemand], kind: str):
    """No pool can be used twice in a week or across split original/trained pools."""
    cap = snapshot.capacity
    pools = []
    for pool in cap.pools:
        if pool.available_hours is None or pool.available_hours < 0:
            return []
        hours = _ceil(Decimal(str(pool.available_hours)))
        rows = [r for r in cap.rows if pool.pool_id in r.pool_ids]
        eligible = tuple(sorted({r.skill_id for r in rows}))
        shifts = tuple(sorted({r.shift_id for r in rows}))
        if not eligible or not shifts:
            continue

        def capacities(active_weeks: set[int], flexible: bool):
            out = {}
            for need in needs:
                week = int(need.interval_id.split(":")[0][1:])
                if week not in active_weeks:
                    continue
                direct = [r for r in rows if (r.skill_id, r.shift_id) == (need.skill, need.shift)]
                if direct:
                    value = max(_ceil(Decimal(str(r.eligible_hours or 0))) for r in direct)
                elif flexible and kind == "reallocate" and need.shift in shifts:
                    # Hypothetical retraining: future cross-skill assignment.
                    value = hours
                elif flexible and kind == "redesign" and need.skill in eligible:
                    # Hypothetical shift redesign: transfer hours, never duplicate them.
                    value = hours
                else:
                    value = 0
                if flexible and ((kind == "reallocate" and need.shift in shifts)
                                 or (kind == "redesign" and need.skill in eligible)):
                    value = max(value, hours)
                if value > 0:
                    out[need.interval_id] = min(hours, value)
            return out

        # Training/shift transition starts only on the third forecast week.
        split = kind in {"reallocate", "redesign"} and len({n.start for n in needs}) >= 3
        periods = len({n.start for n in needs})
        if split:
            phases = [
                (pool.pool_id + "-before", {1, 2}, False),
                (pool.pool_id + "-after", set(range(3, periods + 1)), True),
            ]
        else:
            phases = [(pool.pool_id, set(range(1, periods + 1)), False)]
        for identifier, active, flexible in phases:
            limits = capacities(active, flexible)
            allowed_skills = tuple(sorted({n.skill for n in needs if n.interval_id in limits}))
            allowed_shifts = tuple(sorted({n.shift for n in needs if n.interval_id in limits}))
            if not limits:
                continue
            pools.append(ExistingPool(
                pool_id=identifier, eligible_skills=allowed_skills,
                eligible_shifts=allowed_shifts,
                total_hours=hours * len(active), caps_by_interval=limits,
                qualified=True, schedule_verified=True,  # ASSUMED for what-if ONLY
            ))
    return pools


def _roles(snapshot: SnapshotData, needs: list[IntervalDemand], kind: str, start):
    if kind not in {"hire", "temporary"}:
        return [], ["Sem novo quadro; capacidade redistribuída ou mantida."]
    options = []
    missing_prices = []
    for row in snapshot.capacity.rows:
        if row.cost_max is None or row.currency != "BRL":
            missing_prices.append(f"{row.skill_id}:{row.shift_id}")
            continue
        # An upper hourly aggregate cost is not an individual wage.
        weekly = 32 if kind == "temporary" else 40
        period_weeks = len({n.start for n in needs})
        multiplier = Decimal("1.35") if kind == "temporary" else Decimal("1.00")
        cost = _ceil(Decimal(str(row.cost_max)) * weekly * period_weeks * multiplier * 100)
        # Illustrative 7-day temporary/14-day permanent lead times; not promises.
        ready = start + timedelta(days=7 if kind == "temporary" else 14)
        options.append(HiringOption(
            role_id=f"{kind}-{row.skill_id}-{row.shift_id}",
            eligible_skills=(row.skill_id,), eligible_shifts=(row.shift_id,),
            ready_on=ready, hours_per_person=weekly, max_people=4,
            cost_cents=cost, ramp_percent=100 if kind == "temporary" else 80,
            modality_verified=True,  # hypothetical only; never legal attestation
        ))
    limitations = ["Custos são cenários de sensibilidade sobre faixas horárias agregadas, não orçamento aprovado."]
    if missing_prices:
        limitations.append("Custo por função/turno ausente: " + ", ".join(missing_prices))
    return options, limitations


def build_whatifs(snapshot: SnapshotData, forecast: ForecastResult,
                  aggregates: dict, history: list[dict] | None = None) -> dict[str, dict]:
    """Compute five comparable CP-SAT results; returns {} if units/input are unknown."""
    raw_rate = aggregates.get("cases_per_hour")
    if not raw_rate or not forecast.points:
        return {}
    try:
        rate = Decimal(str(raw_rate))
    except Exception:
        return {}
    if not rate.is_finite() or rate <= 0:
        return {}
    history = history or []
    recent = history[-8:]
    measured = [item for item in recent
                if item.get("demand_semantics") == "incoming_plus_unmet"
                and item.get("incoming_cases") is not None
                and item.get("reopened_cases") is not None]
    reopened = sum(Decimal(str(item["reopened_cases"])) for item in measured)
    incoming = sum(Decimal(str(item["incoming_cases"])) for item in measured)
    rework_fraction = (min(Decimal("0.50"), reopened / incoming) if incoming > 0 else Decimal(0))
    needs = _week_needs(snapshot, forecast, rate, rework_fraction)
    if not needs or any(p.available_hours is None for p in snapshot.capacity.pools):
        return {}
    period_start = min(n.start for n in needs)
    raw_cases = sum(Decimal(str(r.quantity)) for r in snapshot.demand.records if r.quantity is not None)
    if raw_cases <= 0:
        return {}
    outcomes = {}
    kinds = ("do_nothing", "hire", "temporary", "reallocate", "redesign")
    for kind in kinds:
        pools = _pools(snapshot, needs, kind)
        options, prices = _roles(snapshot, needs, kind, period_start)
        # Budget is an upper synthetic envelope, NOT a business approval.
        envelope = sum(o.cost_cents * o.max_people for o in options)
        result: CpSatPlan = solve_capacity(
            needs=needs, pools=pools, options=options, budget_cents=envelope,
            policy_evidence_id=None, policy_verified=False,
            simulation_only=True,
        )
        if result.status not in {"optimal", "feasible"}:
            outcomes[kind] = {
                "solver": "ortools-cp-sat", "solver_status": result.status,
                "approval_ready": False, "reason": list(result.limitations), "weeks": [],
                "incremental_cost_brl": None, "headcount": None, "residual_hours": None,
            }
            continue
        buckets = []
        for week in range(1, len(forecast.points) + 1):
            ids = [n for n in needs if n.interval_id.startswith(f"w{week}:")]
            rows = []
            for need in ids:
                planned = need.target_hours
                uncovered = result.operational_residual.get(need.interval_id, planned)
                rows.append({
                    "skill": need.skill, "shift": need.shift, "target_hours": planned,
                    "covered_hours": max(0, planned - uncovered),
                    "uncovered_hours": uncovered,
                })
            buckets.append({
                "week": week, "starts": forecast.points[week - 1].period.start.isoformat(),
                "skills_shifts": rows, "target_hours": sum(r["target_hours"] for r in rows),
                "uncovered_hours": sum(r["uncovered_hours"] for r in rows),
                "backlog_cases_sensitivity": _ceil(
                    Decimal(sum(r["uncovered_hours"] for r in rows)) * rate
                ),
            })
        cost = result.total_hiring_cost_cents or 0
        # Illustrative fixed reorganization costs apply to demo only.
        synthetic_only = snapshot.source.reference.startswith("alinia-demo-")
        if kind in {"reallocate", "redesign"} and synthetic_only:
            cost = 48000 if kind == "reallocate" else 32000
        elif kind in {"reallocate", "redesign"}:
            cost = 0  # not known: null below
        known_cost = (kind == "do_nothing" or
                      (kind in {"hire", "temporary"} and bool(options) and not any("ausente" in x for x in prices)) or
                      (kind in {"reallocate", "redesign"} and synthetic_only))
        outcomes[kind] = {
            "solver": "ortools-cp-sat", "solver_status": result.status,
            "approval_ready": False, "simulation_only": True,
            "source_snapshot": snapshot.capacity.data_snapshot_id,
            "forecast_status": forecast.status,
            "forecast_method": forecast.method,
            "rework_fraction": float(rework_fraction),
            "backlog_last_observed": (int(history[-1]["backlog_end"])
                                     if history and history[-1].get("backlog_end") is not None else None),
            "week_count": len(buckets), "weeks": buckets,
            "incremental_cost_brl": float(Decimal(cost) / Decimal(100)) if known_cost else None,
            "headcount": sum(result.hires.values()) if kind in {"hire", "temporary"} and options else None,
            "residual_hours": sum(result.operational_residual.values()),
            "assumptions": [
                "Projeção por competência distribuída conforme proporção do último snapshot.",
                "Distribuição de demanda entre turnos é hipótese uniforme; demanda real por turno não informada.",
                "Sem atestado de jornada, cobertura mínima, modalidade contratual ou orçamento.",
                "Lead times, mobilidade e ramp-up são hipóteses exploratórias.",
                "Reaberturas históricas aumentam a carga prevista; não são novas chegadas.",
                f"Fator adicional por reabertura estimado: {rework_fraction:.3f}.",
                "Nenhum resultado autoriza contratação ou mudança de escala.",
                *prices, *list(result.limitations),
            ],
        }
    return outcomes
