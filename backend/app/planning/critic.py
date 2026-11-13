"""Review a scenario. A gap stays a gap; the critic does not approve anything."""
from uuid import uuid4

from backend.app.planning.schemas import CriticResult, ScenarioCandidate, SimulationResult


def critique(*, scenario: ScenarioCandidate, simulation: SimulationResult, policy_complete: bool,
             forecast_status: str, already_asked: bool) -> CriticResult:
    blocks = ["restricao_dura"] if simulation.status == "infeasible" else []
    if scenario.quantitative:
        checks = scenario.quantitative.get("validation", {})
        if checks.get("mathematical_status") == "invalid":
            blocks.append("alocacao_quantitativa_inconsistente")
    missing = []
    if simulation.status in {"unknown", "blocked"}:
        missing.append("solver_sem_resultado")
    if not policy_complete:
        missing.append("policy_review")
    if forecast_status == "abstained":
        missing.append("forecast_history")
    if blocks:
        verdict = "blocked"
    elif missing:
        verdict = "needs_data"
    else:
        verdict = "noted"
    return CriticResult.model_validate({
        "schema_version": "1.0", "review_id": str(uuid4()), "scenario_id": scenario.scenario_id,
        "tenant_id": scenario.tenant_id, "team_id": scenario.team_id, "verdict": verdict,
        "risks": [], "blocks": blocks, "missing_data": missing,
        "hard_constraint_failed": bool(blocks),
        "revision_requested": forecast_status == "abstained" and scenario.kind == "do_nothing" and not already_asked,
    })
