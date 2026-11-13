"""Weekly capacity projections on a common forecast, with explicit intervention assumptions."""
from datetime import timedelta
from decimal import Decimal, InvalidOperation, ROUND_CEILING

from backend.app.contracts.v1 import ForecastResult
from backend.app.data.schemas import SnapshotData
from backend.app.optimization.cpsat_v42 import ExistingPool, HiringOption, IntervalDemand, solve_capacity
from backend.app.optimization.validator_v42 import verify_projection
from backend.app.planning.queues import simulate_queues

KINDS = ("do_nothing", "hire", "temporary", "reallocate", "redesign")
OBJECTIVE = "Minimizar horas descobertas no horizonte; em empate, minimizar custo de contratação."


def _ceil(value):
    return int(value.to_integral_value(rounding=ROUND_CEILING))


def _point_value(point):
    return Decimal(str(point.p50 if point.p50 is not None else point.point_estimate))


def _quality(history):
    recent = [row for row in history[-8:] if row.get("demand_semantics") == "incoming_plus_unmet"]
    incoming = sum(int(row["incoming_cases"]) for row in recent)
    return Decimal(sum(int(row["reopened_cases"]) for row in recent)) / incoming if incoming else None


def _grid(snapshot, forecast, rate, rework, history, mandatory):
    quantities = {item.skill_id: Decimal(str(item.quantity)) for item in snapshot.demand.records
                  if item.quantity is not None}
    if len(quantities) != len(snapshot.demand.records) or not quantities:
        return None
    rejected_segments = {(segment.skill_id, segment.shift_id) for segment in forecast.segments
                         if segment.points and not segment.usable_for_planning}
    segments = {(segment.skill_id, segment.shift_id): segment for segment in forecast.segments
                if segment.usable_for_planning and len(segment.points) == len(forecast.points)}
    latest = history[-1] if history else {}
    latest_segments = {(row["skill_id"], row["shift_id"]): row for row in latest.get("segments", [])}
    assumptions = set()
    initial = {}
    arrivals = {}
    needs = []
    for skill, quantity in sorted(quantities.items()):
        shifts = sorted({row.shift_id for row in snapshot.capacity.rows if row.skill_id == skill})
        if not shifts:
            return None
        if any((skill, shift) in rejected_segments for shift in [None, *shifts]):
            return None
        shift_series = all((skill, shift) in segments for shift in shifts)
        if shift_series:
            weights = {}
            assumptions.add("Demanda por turno prevista a partir de séries observadas.")
        else:
            measured = {shift: latest_segments.get((skill, shift), {}).get("quantity") for shift in shifts}
            total = sum(Decimal(value) for value in measured.values() if value is not None)
            if total and all(value is not None for value in measured.values()):
                weights = {shift: Decimal(value) / total for shift, value in measured.items()}
                assumptions.add("Rateio por turno usa as proporções observadas na última semana.")
            else:
                weights = {shift: Decimal(1) / len(shifts) for shift in shifts}
                assumptions.add("Rateio uniforme por turno é hipótese sem observação por turno.")
        if not shift_series and (skill, None) not in segments:
            if not sum(quantities.values()):
                return None
            assumptions.add("Rateio por competência usa a proporção do último snapshot.")
        for index, point in enumerate(forecast.points):
            for shift in shifts:
                key = (skill, shift)
                if shift_series:
                    cases = _point_value(segments[key].points[index])
                elif (skill, None) in segments:
                    cases = _point_value(segments[(skill, None)].points[index]) * weights[shift]
                else:
                    cases = _point_value(point) * quantity / sum(quantities.values()) * weights[shift]
                identifier = f"{index}:{len(needs)}"
                if index == 0:
                    backlog = latest_segments.get(key, {}).get("backlog_end")
                    skill_backlog = latest_segments.get((skill, None), {}).get("backlog_end")
                    initial[key] = (Decimal(backlog) if backlog is not None else
                                    Decimal(skill_backlog) / len(shifts) if skill_backlog is not None else None)
                    if backlog is None and skill_backlog is not None:
                        assumptions.add("Backlog inicial por turno rateado uniformemente a partir da competência.")
                opening = (initial[key] or Decimal(0)) if index == 0 else Decimal(0)
                arrivals[identifier] = cases
                work = cases * (1 + (rework or 0)) + opening
                minimum = mandatory.get(key, 0)
                needs.append(IntervalDemand(identifier, point.period.start, point.period.end_exclusive,
                                            skill, shift, minimum, max(minimum, _ceil(work / rate))))
    return needs, initial, arrivals, sorted(assumptions)


def _pools(snapshot, needs, kind, premises):
    windows = sorted({(need.start, need.end_exclusive) for need in needs})
    pools = []
    transitions = []
    rows = {(row.skill_id, row.shift_id): row for row in snapshot.capacity.rows}
    # Mobility is explicitly a demo premise. Real snapshots require authorized
    # evidence of which pools may move and their permitted destinations.
    demo = snapshot.source.kind == "synthetic" and (premises is None or premises.mobility is None)
    configured = {item.pool_id: item for item in (premises.mobility or []) if item.kind == kind} if premises else {}
    for pool in sorted(snapshot.capacity.pools, key=lambda pool: pool.pool_id):
        hours = int(pool.available_hours)
        direct = {key for key, row in rows.items() if pool.pool_id in row.pool_ids}
        skills = {skill for skill, _ in direct}
        shifts = {shift for _, shift in direct}
        flex = set()
        overhead = 0
        week_ready = 1
        move_cap = hours // 4
        transition_cost = None
        selected = configured.get(pool.pool_id)
        if selected:
            flex = {(selected.target_skill, selected.target_shift)}
            overhead = selected.training_and_mentoring_hours_per_week
            week_ready = selected.transition_weeks
            move_cap = selected.transferable_hours_per_week
            if selected.cost_min_brl is not None:
                transition_cost = (selected.cost_min_brl, selected.cost_max_brl)
        if demo and pool.pool_id == "pool-atendimento" and kind == "reallocate":
            flex = {("especializado", shift) for shift in shifts} & rows.keys() - direct
            overhead = min(8, hours)
            week_ready = 2
            transition_cost = (480, 900)
        if demo and pool.pool_id == "pool-atendimento" and kind == "redesign":
            flex = {(skill, "noite") for skill in skills} & rows.keys() - direct
            overhead = min(4, hours)
            move_cap = hours // 3
            transition_cost = (320, 620)
        limits = {}
        flexible = []
        window_limits = dict.fromkeys(windows, hours)
        flex_limits = dict.fromkeys(windows, 0)
        if flex and move_cap:
            for window in windows[:week_ready]:
                window_limits[window] -= overhead
            for index, window in enumerate(windows[week_ready:]):
                flex_limits[window] = move_cap // 2 if kind == "reallocate" and index == 0 else move_cap
            transitions.append({
                "pool": pool.pool_id, "cost_range_brl": list(transition_cost) if transition_cost else None, "source": [list(key) for key in sorted(direct)],
                "destinations": [list(key) for key in sorted(flex)],
                "implementation_days": 7 * week_ready,
                "training_and_mentoring_hours": overhead * min(week_ready, len(windows)),
                "transferable_hours_per_week": move_cap,
                "initial_transferable_hours": move_cap // 2 if kind == "reallocate" else move_cap,
            })
        for need in needs:
            key = (need.skill, need.shift)
            window = (need.start, need.end_exclusive)
            if key in direct:
                limits[need.interval_id] = min(hours, int(rows[key].eligible_hours))
            elif key in flex and flex_limits[window]:
                limits[need.interval_id] = min(flex_limits[window], int(rows[key].eligible_hours))
                flexible.append(need.interval_id)
        pools.append(ExistingPool(
            pool.pool_id, tuple(sorted(skills | {skill for skill, _ in flex})),
            tuple(sorted(shifts | {shift for _, shift in flex})), sum(window_limits.values()), limits,
            schedule_verified=True, caps_by_window=window_limits, flexible_caps_by_window=flex_limits,
            flexible_intervals=tuple(flexible),
        ))
    return pools, transitions


def _roles(snapshot, needs, kind):
    if kind not in {"hire", "temporary"}:
        return [], {}, [], {}
    start = min(n.start for n in needs)
    end = max(n.end_exclusive for n in needs)
    permanent = kind == "hire"
    phases = {"recruitment_days": 7 if permanent else 4, "admission_days": 3 if permanent else 1,
              "training_days": 4 if permanent else 2}
    ready = start + timedelta(days=sum(phases.values()))
    expires = ready + timedelta(weeks=2) if not permanent else None
    weekly = 40 if permanent else 32
    paid_weeks = max(0, (min(end, expires or end) - ready).days // 7)
    ramp = (60, 85, 100) if permanent else (85, 100)
    options, prices, missing = [], {}, []
    for index, row in enumerate(sorted(snapshot.capacity.rows, key=lambda row: (row.skill_id, row.shift_id))):
        if row.cost_min is None or row.cost_max is None or row.currency != "BRL":
            missing.append(f"{row.skill_id}/{row.shift_id}")
            continue
        if not paid_weeks:
            continue
        multiplier = Decimal("1.30") if not permanent else Decimal(1)
        # Hourly rates are aggregate cost assumptions. Onboarding is charged once.
        onboarding = (600, 1100) if permanent else (180, 350)
        low = _ceil((Decimal(str(row.cost_min)) * weekly * paid_weeks * multiplier + onboarding[0]) * 100)
        high = _ceil((Decimal(str(row.cost_max)) * weekly * paid_weeks * multiplier + onboarding[1]) * 100)
        role = f"{kind}-{index}"
        prices[role] = (low, high)
        mentor = sorted(row.pool_ids)[0] if row.pool_ids else None
        options.append(HiringOption(
            role, (row.skill_id,), (row.shift_id,), ready, weekly, 4, high, 100,
            mentor_pool_id=mentor, mentor_hours_per_hire=4 if mentor else 0, modality_verified=True,
            ends_before=expires, weekly_ramp_percent=ramp,
        ))
    schedule = {**phases, "implementation_days": sum(phases.values()), "ready_on": ready.isoformat(),
                "ends_before": expires.isoformat() if expires else None, "weekly_ramp_percent": list(ramp),
                "paid_weeks_in_horizon": paid_weeks}
    return options, prices, missing, schedule


def _project(needs, result, rate, rework, initial, arrivals):
    backlog = dict(initial)
    weeks = {}
    for need in needs:
        skill_shift = (need.skill, need.shift)
        uncovered = result.operational_residual[need.interval_id]
        served = need.target_hours - uncovered
        start = need.start.isoformat()
        week = weeks.setdefault(start, {"starts": start, "skills_shifts": []})
        prior = backlog[skill_shift]
        # Report the carried workload in case equivalents. Rework is extra
        # service demand and is not a second incoming case in the ledger.
        work = arrivals[need.interval_id] * (1 + (rework or 0))
        if prior is not None:
            backlog[skill_shift] = max(Decimal(0), prior + work - Decimal(served) * rate)
        week["skills_shifts"].append({
            "skill": need.skill, "shift": need.shift,
            "arrival_cases": float(arrivals[need.interval_id]), "target_hours": need.target_hours,
            "mandatory_hours": need.mandatory_hours,
            "covered_hours": served, "uncovered_hours": uncovered,
            "backlog_cases": None if backlog[skill_shift] is None else float(backlog[skill_shift]),
        })
    for index, week in enumerate(weeks.values(), 1):
        rows = week["skills_shifts"]
        week["week"] = index
        for key in ("target_hours", "covered_hours", "uncovered_hours", "arrival_cases"):
            week[key] = sum(row[key] for row in rows)
        week["backlog_cases"] = (sum(row["backlog_cases"] for row in rows)
                                 if all(row["backlog_cases"] is not None for row in rows) else None)
    return list(weeks.values())


def build_whatifs(snapshot: SnapshotData, forecast: ForecastResult, aggregates: dict,
                  history: list[dict] | None = None, *, premises=None) -> dict[str, dict]:
    history = history or []
    cap = snapshot.capacity
    try:
        rate = Decimal(str(aggregates["cases_per_hour"])) if aggregates.get("cases_per_hour") else None
    except InvalidOperation:
        rate = None
    context = {
        "solver": "ortools-cp-sat", "approval_ready": False, "simulation_only": True,
        "source_snapshot": cap.data_snapshot_id, "source_kind": snapshot.source.kind,
        "source_version": snapshot.source.version,
        "synthetic": snapshot.source.kind == "synthetic", "forecast_status": forecast.status,
        "forecast_method": forecast.method, "forecast_version": forecast.model_version,
        "horizon": forecast.horizon.model_dump(mode="json"), "objective": OBJECTIVE,
        "target_basis": "P50 por série calibrada; estimativa diagnóstica para as demais séries elegíveis.",
        "premise_source": ("rh_reviewed" if premises is not None else
                           "synthetic_fixture" if snapshot.source.kind == "synthetic" else "default_exploratory"),
        "demand_semantics": history[-1].get("demand_semantics") if history else None,
    }
    def unavailable(reason):
        return {kind: {**context, "solver_status": "blocked", "reason": [reason], "weeks": [],
                       "incremental_cost_brl": None, "cost_status": "unavailable", "headcount": None,
                       "residual_hours": None, "validation": {"status": "blocked", "violations": [reason]}}
                for kind in KINDS}

    if not rate or not rate.is_finite() or rate <= 0 or not forecast.points or not forecast.usable_for_planning:
        return unavailable("DEMANDA_FUTURA_OU_PRODUTIVIDADE_INDISPONIVEL")
    if (forecast.data_snapshot_id != cap.data_snapshot_id or forecast.tenant_id != cap.tenant_id
            or forecast.team_id != cap.team_id or forecast.horizon.timezone != cap.period.timezone
            or any(item.period != cap.period for item in snapshot.demand.records)):
        return unavailable("UNIDADES_OU_RECORTE_INCOMPATIVEIS")
    if ((cap.period.end_exclusive - cap.period.start).days != 7
            or cap.period.end_exclusive != forecast.history_end_exclusive
            or any(p.available_hours is None for p in cap.pools)
            or any(r.eligible_hours is None for r in cap.rows)):
        return unavailable("CAPACIDADE_SEMANAL_OU_ELEGIBILIDADE_INDISPONIVEL")
    rework = _quality(history)
    mandatory = {(row["skill"], row["shift"]): row["hours"] for row in aggregates.get("mandatory_hours", [])}
    grid = _grid(snapshot, forecast, rate, rework, history, mandatory)
    if grid is None:
        return unavailable("MATRIZ_DE_DEMANDA_INCOMPLETA")
    needs, initial, arrivals, assumptions = grid
    row_caps = {(r.skill_id, r.shift_id): int(r.eligible_hours) for r in cap.rows}
    interval_caps = {n.interval_id: row_caps[(n.skill, n.shift)] for n in needs}
    outcomes = {}
    if premises is not None and not premises.applies_to(snapshot):
        return unavailable("PREMISSAS_INCOMPATIVEIS_COM_SNAPSHOT")
    need_by_id = {need.interval_id: need for need in needs}
    windows = sorted({(need.start, need.end_exclusive) for need in needs})
    for kind in KINDS:
        pools, transitions = _pools(snapshot, needs, kind, premises)
        options, prices, missing, schedule = _roles(snapshot, needs, kind)
        budget = sum(option.cost_cents * option.max_people for option in options)
        if premises is not None and premises.hiring_budget_brl is not None:
            budget = min(budget, int(Decimal(str(premises.hiring_budget_brl)) * 100))
        result = solve_capacity(needs=needs, pools=pools, options=options, budget_cents=budget,
                                policy_evidence_id=None, policy_verified=False, simulation_only=True,
                                existing_interval_caps=interval_caps)
        success = result.status in {"optimal", "feasible"}
        validation = verify_projection(needs, pools, options, interval_caps, result)
        success = success and validation["mathematical_status"] == "verified"
        weeks = _project(needs, result, rate, rework, initial, arrivals) if success else []
        for week, window in zip(weeks, windows):
            mentoring = sum(o.mentor_hours_per_hire * result.hires[o.role_id] for o in options
                            if window[0] < o.ready_on <= window[1])
            week["available_hours"] = (sum(p.caps_by_window[window] for p in pools) - mentoring
                                       + sum(o.effective_hours(*window) * result.hires[o.role_id] for o in options))
            week["moved_hours"] = sum(
                hours for p in pools for key, hours in result.pool_allocations[p.pool_id].items()
                if key in p.flexible_intervals and need_by_id[key].start == window[0]
            )
        if weeks and schedule:
            for week in weeks:
                active = schedule["ready_on"] <= week["starts"] and (
                    schedule["ends_before"] is None or week["starts"] < schedule["ends_before"]
                )
                week["incremental_cost_brl"] = (
                    sum(prices[role][1] * count / 100 for role, count in result.hires.items())
                    / schedule["paid_weeks_in_horizon"] if active and not missing else None if missing else 0
                )
        if weeks and kind == "do_nothing":
            for week in weeks:
                week["incremental_cost_brl"] = 0
        costs = None
        if success and kind == "do_nothing":
            costs = (0, 0)
        elif success and kind in {"hire", "temporary"} and not missing:
            costs = tuple(sum(prices[role][i] * count for role, count in result.hires.items()) / 100
                          for i in (0, 1))
        elif success and transitions and all(t["cost_range_brl"] is not None for t in transitions):
            costs = tuple(sum(t["cost_range_brl"][index] for t in transitions) for index in (0, 1))
            for index, week in enumerate(weeks):
                week["incremental_cost_brl"] = costs[1] if index == 0 else 0
        outcomes[kind] = {
            **context, "solver_status": result.status, "validation": validation, "weeks": weeks,
            "intervention_status": ("missing_cost_inputs" if missing else "mobility_evidence_missing"
                                    if kind in {"reallocate", "redesign"} and not transitions else "modeled"),
            "mandatory_grid": "partial_or_supplied" if mandatory else "unavailable",
            "rework_fraction": None if rework is None else float(rework),
            "backlog_last_observed": int(history[-1]["backlog_end"]) if history and "backlog_end" in history[-1] else None,
            "incremental_cost_brl": costs[1] if costs else None,
            "cost_range_brl": {"min": costs[0], "max": costs[1]} if costs else None,
            "cost_status": ("known_baseline" if kind == "do_nothing" and costs else
                            "assumed" if costs else "unavailable"),
            "headcount": sum(result.hires.values()) if success and options and not missing else None,
            "cost_per_hour_saved_brl": None,
            "role_mix": [{"skill": option.eligible_skills[0], "shift": option.eligible_shifts[0],
                          "people": result.hires.get(option.role_id, 0)}
                         for option in options if result.hires.get(option.role_id, 0)],
            "lead_time": schedule or None, "transitions": transitions,
            "implementation_days": schedule.get("implementation_days") if schedule else (
                max(t["implementation_days"] for t in transitions) if transitions else
                0 if kind == "do_nothing" else None),
            "residual_hours": sum(result.operational_residual.values()) if success else None,
            "reason": list(result.limitations),
            "solver_version": result.solver_version,
            "seed": 42,
            "hiring_budget_brl": premises.hiring_budget_brl if premises and kind in {"hire", "temporary"} else None,
            "assumptions": [
                *assumptions,
                "Disponibilidade do último snapshot repetida semanalmente. Limites físicos arredondados para baixo.",
                ("Mínimos informados são restrições duras na simulação; aplicabilidade requer revisão."
                 if mandatory else "Mínimos de cobertura ausentes; orçamento e jornadas requerem revisão."),
                "Backlog em casos equivalentes: saldo anterior + chegadas e retrabalho − serviço comprometido.",
                "Não há alocação adicional de horas para limpar saldo futuro além do compromisso semanal modelado.",
                *([f"Custos ausentes em {', '.join(missing)}. Opções sem custo foram excluídas."] if missing else []),
            ],
            "queue": simulate_queues(weeks, rate, rework, initial, aggregates),
        }
    baseline = outcomes["do_nothing"]["residual_hours"]
    for outcome in outcomes.values():
        residual = outcome["residual_hours"]
        saved = baseline - residual if baseline is not None and residual is not None else None
        outcome["hours_saved_vs_baseline"] = saved
        if saved and saved > 0 and outcome["cost_range_brl"]:
            outcome["cost_per_hour_saved_brl"] = {
                key: round(value / saved, 2) for key, value in outcome["cost_range_brl"].items()
            }
    return outcomes
