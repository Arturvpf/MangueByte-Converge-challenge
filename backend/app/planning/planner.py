"""Three scenarios. Headcount is copied from the solver and the approved weekly cap."""
from hashlib import sha256
import json
from uuid import uuid4

from backend.app.optimization.solver import Row, solve
from backend.app.planning.schemas import AllocationOut, ScenarioCandidate, SimulationResult


def _seal(payload: dict) -> ScenarioCandidate:
    body = {key: value for key, value in payload.items() if key != "content_hash"}
    payload["content_hash"] = sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    return ScenarioCandidate.model_validate(payload)


def _simulation(scenario_id, tenant_id, team_id, snapshot_id, result, assumptions) -> SimulationResult:
    return SimulationResult.model_validate({
        "schema_version": "1.0", "simulation_id": str(uuid4()), "scenario_id": scenario_id,
        "tenant_id": tenant_id, "team_id": team_id, "data_snapshot_id": snapshot_id,
        "status": result.status,
        "allocations": [AllocationOut(pool_id=item.pool_id, skill_id=item.skill_id, shift_id=item.shift_id, hours=item.hours)
                        for item in result.allocations],
        "residual_hours": dict(result.residual_hours),
        "limitations": list(result.limitations),
        "assumptions": assumptions,
    })


def _unknown(scenario_id, tenant_id, team_id, snapshot_id, skills):
    class _Result:
        status = "unknown"
        allocations = ()
        residual_hours = {skill: 0 for skill in skills}
        limitations = ("demanda ou produtividade ausente; o solver não rodou",)
        cost = None
    return _simulation(scenario_id, tenant_id, team_id, snapshot_id, _Result(), ["solver não executado"])


def build_scenarios(*, tenant_id: str, team_id: str, snapshot_id: str, pools: dict[str, int], rows: list[Row],
                    demand_hours: dict[str, int] | None, weekly_max: int | None, policy_complete: bool,
                    forecast_calibrated: bool, dependencies: list[str], rule_versions: list[str]):
    skills = sorted({row.skill_id for row in rows})
    reliable = demand_hours is not None and policy_complete and forecast_calibrated
    base = solve(pools, rows, demand_hours) if demand_hours is not None else None
    scenarios = []

    def add(kind, result, actions, gaps, headcount, assumptions):
        scenario_id = str(uuid4())
        residual = None if result is None else sum(result.residual_hours.values())
        if residual:
            assumptions = [*assumptions, "backlog operacional igual ao residual de horas; não é simulação de fila"]
        conclusive = reliable and result is not None and result.status in {"optimal", "feasible"}
        if kind == "hire":
            # A successful max-flow search is not evidence that every required skill is covered.
            conclusive = (conclusive and headcount is not None and weekly_max is not None
                          and residual == 0 and not gaps)
        scenario = _seal({
            "schema_version": "1.0", "scenario_id": scenario_id, "tenant_id": tenant_id, "team_id": team_id,
            "data_snapshot_id": snapshot_id, "kind": kind, "version": 1, "actions": actions,
            "assumptions": assumptions, "dependencies": list(dependencies), "gaps": gaps,
            "preliminary_cost": None,  # No validated role/contract cost inputs in this pilot.
            "headcount_delta": headcount, "residual_hours": residual, "conclusive": conclusive,
            "content_hash": "0" * 64, "rule_versions": list(rule_versions),
        })
        simulation = (_simulation(scenario_id, tenant_id, team_id, snapshot_id, result, assumptions)
                      if result is not None else _unknown(scenario_id, tenant_id, team_id, snapshot_id, skills))
        scenarios.append((scenario, simulation))

    capacity_gap = [] if forecast_calibrated else ["previsão abstida; nenhum headcount é recomendado"]
    if not policy_complete:
        capacity_gap.append("regra aplicável ausente ou em revisão")
    add("do_nothing", base, ["manter o quadro atual"], capacity_gap, None,
        ["o déficit é o residual do solver sobre as horas atuais"])
    realloc_gaps = list(capacity_gap)
    if len(skills) < 2:
        realloc_gaps.append("não há segunda skill para realocar; a simulação não cria capacidade")
    add("reallocate", base, ["realocar horas já existentes entre as skills elegíveis"], realloc_gaps, None,
        ["a realocação usa o mesmo solver; não inventa hora nova"])
    headcount = None
    hired = base
    hire_assumptions = ["contratação só entra como pool adicional no solver",
                        "Custos de contratação ainda não foram fornecidos; custo permanece desconhecido."]
    if base is not None and weekly_max and forecast_calibrated:
        extra = sum(base.residual_hours.values())
        if extra:
            hired_pools = dict(pools)
            hired_rows = list(rows)
            # New capacity is explicitly skill-specific; it must not be attributed entirely
            # to the largest gap while leaving other required skills uncovered.
            for index, (skill, missing) in enumerate(sorted(base.residual_hours.items())):
                if not missing:
                    continue
                pool_id = f"pool-hire-{index}"
                hired_pools[pool_id] = missing
                hired_rows.append(Row(skill, "hire", (pool_id,), missing))
            hired = solve(hired_pools, hired_rows, demand_hours)
            headcount = (extra + weekly_max - 1) // weekly_max
            hire_assumptions.append("headcount agregado estimado sobre horas faltantes; composição de cargos não validada")
            if len([x for x in base.residual_hours.values() if x > 0]) > 1:
                capacity_gap.append("múltiplas competências: headcount agregado não prova composição contratável ou turnos viáveis")
        else:
            headcount = 0
    elif weekly_max is None:
        hire_assumptions.append("sem jornada semanal aprovada, o headcount fica vazio")
    add("hire", hired, ["adicionar capacidade nova e recalcular o residual"], capacity_gap, headcount, hire_assumptions)
    return scenarios
