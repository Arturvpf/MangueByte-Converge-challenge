"""Two investigation paths. Text in the data is evidence, never an instruction."""
from backend.app.contracts.v1 import EvidenceRef, ForecastResult, Hypothesis, InvestigationReport, Question


def build_report(*, tenant_id: str, team_id: str, data_snapshot_id: str, demand_known: bool,
                 history_points: int, notes: list[str]) -> InvestigationReport:
    evidence = EvidenceRef.model_validate({
        "evidence_id": "ev-snapshot", "tenant_id": tenant_id, "team_id": team_id,
        "data_snapshot_id": data_snapshot_id, "description": "Contagem agregada do snapshot, sem pessoas identificadas",
    })
    hypotheses = []
    questions = []
    missing = []
    if demand_known:
        hypotheses.append(Hypothesis.model_validate({
            "hypothesis_id": "hyp-capacity",
            "statement": "O snapshot registra demanda agregada e horas de pool para a equipe",
            "critical": True, "verification": "supported", "evidence_ids": ["ev-snapshot"], "confidence": None,
        }))
    else:
        hypotheses.append(Hypothesis.model_validate({
            "hypothesis_id": "hyp-capacity",
            "statement": "A demanda agregada pode explicar a pressão de capacidade",
            "critical": True, "verification": "unverified", "evidence_ids": [], "confidence": None,
        }))
        missing.append("demanda agregada")
        questions.append(_pending("q-demand", "Qual é a demanda agregada, em atendimentos, no período do snapshot?"))
    hypotheses.append(Hypothesis.model_validate({
        "hypothesis_id": "hyp-coverage",
        "statement": "A cobertura pode ser desigual entre competências e turnos",
        "critical": True, "verification": "unverified", "evidence_ids": [], "confidence": None,
    }))
    questions.append(_pending("q-skill", "Quais tarefas dessa equipe exigem cada competência no turno registrado?"))
    missing.append("cobertura por competência e turno")
    if history_points < 8:
        hypotheses.append(Hypothesis.model_validate({
            "hypothesis_id": "hyp-seasonality",
            "statement": "O desvio pode ser um pico transitório",
            "critical": True, "verification": "unverified", "evidence_ids": [], "confidence": None,
        }))
        questions.append(_pending("q-history", "Há histórico comparável de pelo menos oito períodos?"))
        missing.append("histórico comparável")
    return InvestigationReport.model_validate({
        "schema_version": "1.0", "tenant_id": tenant_id, "team_id": team_id, "data_snapshot_id": data_snapshot_id,
        "trigger": "demanda registrada no snapshot" if demand_known else "snapshot sem quantidade de demanda",
        "hypotheses": hypotheses, "missing_data": missing, "confidence_label": "low" if demand_known else "unknown",
        "evidence_refs": [evidence], "questions": questions,
        "limitations": [*notes, "Nenhuma hipótese vira instrução de acesso ou de contratação."],
        "confidence": None,
    })


def _pending(question_id: str, text: str) -> Question:
    return Question.model_validate({"question_id": question_id, "text": text, "status": "pending", "answer": None})


def apply_answer(report: InvestigationReport, question_id: str, answer: str) -> InvestigationReport:
    """Store the answer as text. It does not change verification of unsupported hypotheses."""
    payload = report.model_dump(mode="json")
    matched = False
    for question in payload["questions"]:
        if question["question_id"] == question_id:
            question["status"] = "answered"
            question["answer"] = answer
            matched = True
    if not matched:
        raise KeyError(question_id)
    return InvestigationReport.model_validate(payload)


def forecast_status(forecast: ForecastResult | None) -> str:
    return "abstained" if forecast is None else forecast.status
