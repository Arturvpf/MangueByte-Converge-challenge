"""Moving-median baseline plus rolling-origin predictive quantiles with holdout gating."""
from datetime import date, timedelta
from decimal import Decimal

from backend.app.contracts.v1 import Backtest, ForecastPoint, ForecastResult, Period

MODEL_VERSION = "baseline-moving-median-1"
NOT_A_PERCENTILE = "A faixa simultânea não equivale aos percentis preditivos P10/P50/P90."


def predict_next(values: list[Decimal]) -> Decimal:
    """Median of the last four observations. The caller must pass only the past."""
    window = sorted(values[-4:])
    middle = len(window) // 2
    if len(window) % 2:
        return window[middle]
    return (window[middle - 1] + window[middle]) / 2


def _quantile(values: list[Decimal], probability: Decimal) -> Decimal:
    """Type-7 empirical quantile on residuals, no extrapolation."""
    ordered = sorted(values)
    if not ordered:
        raise ValueError("No calibration observations")
    position = (len(ordered) - 1) * probability
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _backtest(values: list[Decimal]):
    errors = []
    actuals = []
    for index in range(8, len(values)):
        predicted = predict_next(values[:index])
        errors.append(abs(predicted - values[index]))
        actuals.append(values[index])
    if not errors:
        return None, None, []
    mae = sum(errors) / len(errors)
    denominator = sum(abs(item) for item in actuals)
    wape = None if denominator == 0 else sum(errors) / denominator
    return mae, wape, errors


def forecast_series(*, tenant_id: str, team_id: str, data_snapshot_id: str, timezone: str,
                    observations: list[tuple[date, date, Decimal | None]]) -> ForecastResult:
    ordered = sorted(observations, key=lambda item: item[0])
    limitations = [NOT_A_PERCENTILE, "Baseline de mediana móvel; não é modelo sazonal calibrado por domínio."]
    end = ordered[-1][1] if ordered else date(2026, 1, 1)
    horizon = Period(start=end, end_exclusive=end + timedelta(days=28), timezone=timezone)
    enough = len(ordered) >= 8 and all(item[2] is not None for item in ordered)
    overlaps = any(ordered[i][1] > ordered[i + 1][0] for i in range(len(ordered) - 1))
    irregular = any(
        (end_day - start_day).days != 7 or (index and ordered[index - 1][1] != start_day)
        for index, (start_day, end_day, _) in enumerate(ordered)
    )
    if not enough or overlaps or irregular or not ordered:
        if overlaps:
            limitations.append("Períodos sobrepostos; a série foi recusada.")
        elif irregular:
            limitations.append("Série com lacunas ou períodos não semanais; previsão abstida.")
        elif len(ordered) < 8:
            limitations.append("Histórico com menos de 8 períodos; previsão abstida.")
        else:
            limitations.append("Quantidade ausente; previsão abstida.")
        return ForecastResult.model_validate({
            "schema_version": "1.0", "tenant_id": tenant_id, "team_id": team_id,
            "data_snapshot_id": data_snapshot_id, "model_version": MODEL_VERSION, "method": "abstained",
            "status": "abstained", "unit": "cases_per_period", "history_end_exclusive": end, "horizon": horizon,
            "points": [], "interval_description": None, "backtest": None, "limitations": limitations,
        })
    values = [item[2] for item in ordered]
    estimate = predict_next(values)
    mae, wape, errors = _backtest(values)
    # Rolling-origin multi-step errors: score the *worst* absolute error
    # over the four forecast weeks per origin. A one-step residual cannot
    # justify a four-week prediction interval. Holdout remains untouched
    # when selecting the envelope (conservative empirical, NOT P10/P90).
    interval_width = None
    holdout_coverage = None
    horizon_errors = [
        max(abs(predict_next(values[:index]) - actual) for actual in values[index:index + 4])
        for index in range(8, len(values) - 3)
    ]
    # Purge three origins between calibration and holdout: their four-week
    # evaluation windows would otherwise overlap and leak holdout outcomes.
    if len(horizon_errors) >= 27:
        calibration, holdout = horizon_errors[:-11], horizon_errors[-8:]
        rank = (9 * (len(calibration) + 1) + 9) // 10
        if rank <= len(calibration):
            envelope = sorted(calibration)[rank - 1]
            holdout_coverage = sum(error <= envelope for error in holdout) / len(holdout)
            if holdout_coverage >= 0.875:
                interval_width = envelope
    if wape is None:
        limitations.append("WAPE indefinido porque a soma dos realizados do backtest é zero.")
    status = "calibrated" if interval_width is not None and wape is not None else "uncalibrated"
    if status == "uncalibrated":
        limitations.append("Sem oito origens de holdout e amostra suficiente para validar a faixa conjunta de quatro semanas por equipe.")
    # Train empirical predictive quantiles only on CALIBRATION origins; never
    # use the final eight origins to fit a quantile. Residuals are specific to
    # each forecast lead (week 1, 2, 3, 4), not borrowed from 1-week errors.
    quantile_residuals = [[] for _ in range(4)]
    if interval_width is not None:
        for origin in range(8, len(values) - 3 - 11):
            predicted = predict_next(values[:origin])
            for lead in range(4):
                quantile_residuals[lead].append(values[origin + lead] - predicted)
    points = []
    for week in range(4):
        start = end + timedelta(days=7 * week)
        residuals = quantile_residuals[week]
        q = (tuple(max(Decimal(0), estimate + _quantile(residuals, level))
                    for level in (Decimal("0.10"), Decimal("0.50"), Decimal("0.90")))
             if residuals else (None, None, None))
        points.append(ForecastPoint.model_validate({
            "period": Period(start=start, end_exclusive=start + timedelta(days=7), timezone=timezone),
            "point_estimate": float(estimate),
            "lower": None if interval_width is None else float(max(Decimal(0), estimate - interval_width)),
            "upper": None if interval_width is None else float(estimate + interval_width),
            "p10": None if q[0] is None else float(q[0]),
            "p50": None if q[1] is None else float(q[1]),
            "p90": None if q[2] is None else float(q[2]),
        }))
    if mae is None:
        limitations.append("Sem janela de backtest após os 8 primeiros períodos; estimativa não calibrada.")
    backtest = None
    if mae is not None:
        backtest = Backtest.model_validate({
            "method": "moving_median_4", "evaluated_through": end - timedelta(days=1),
            "mae": float(mae), "wape": None if wape is None else float(wape), "limitations": limitations,
        })
    return ForecastResult.model_validate({
        "schema_version": "1.0", "tenant_id": tenant_id, "team_id": team_id,
        "data_snapshot_id": data_snapshot_id, "model_version": MODEL_VERSION, "method": "moving_median_4",
        "status": status, "unit": "cases_per_period", "history_end_exclusive": end, "horizon": horizon,
        "points": points,
        "interval_description": None if interval_width is None else (
            "Faixa empírica simultânea de quatro semanas por origem, com calibração temporal separada do teste; "
            f"cobertura de holdout {holdout_coverage:.0%}; não é P10/P50/P90 nem garantia."
        ),
        "backtest": backtest, "limitations": limitations,
    })
