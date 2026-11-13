"""Weekly rolling-origin forecasts with disjoint calibration and evaluation targets."""
from datetime import date, timedelta
from decimal import Decimal
from statistics import median

from backend.app.contracts.v1 import Backtest, ForecastPoint, ForecastResult, Period

MODEL_VERSION = "weekly-empirical-2"
NOT_A_PERCENTILE = "A faixa simultânea não equivale aos percentis preditivos P10/P50/P90."
LEVELS = (Decimal("0.10"), Decimal("0.50"), Decimal("0.90"))
MIN_ORIGIN = 8
HOLDOUT_ORIGINS = 8
MIN_CALIBRATION = 16


def predict_next(values: list[Decimal]) -> Decimal:
    return median(values[-4:])


def _quantile(values, probability):
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _predict(values, weeks, lag):
    if lag is None or len(values) < lag:
        return [predict_next(values)] * weeks
    return [values[-lag + lead % lag] for lead in range(weeks)]


def _errors(values, origins, weeks, lag):
    return [
        [actual - estimate for actual, estimate in zip(
            values[origin:origin + weeks], _predict(values[:origin], weeks, lag),
        )]
        for origin in origins
    ]


def _metrics(errors, actuals):
    if not errors:
        return {"mae": None, "wape": None}
    absolute = sum(abs(error) for error in errors)
    total = sum(actuals)
    return {"mae": float(absolute / len(errors)), "wape": float(absolute / total) if total else None}


def _positive(estimate):
    return max(Decimal(0), estimate)


def forecast_series(*, tenant_id: str, team_id: str, data_snapshot_id: str, timezone: str,
                    observations: list[tuple[date, date, Decimal | None]], weeks: int = 4,
                    source_kind: str | None = None) -> ForecastResult:
    if not 1 <= weeks <= 12:
        raise ValueError("horizon must be between one and twelve weeks")
    ordered = sorted(observations, key=lambda item: item[0])
    end = ordered[-1][1] if ordered else date(2026, 1, 1)
    horizon = Period(start=end, end_exclusive=end + timedelta(weeks=weeks), timezone=timezone)
    limitations = [NOT_A_PERCENTILE]
    scope = dict(schema_version="1.0", tenant_id=tenant_id, team_id=team_id, data_snapshot_id=data_snapshot_id,
                 model_version=MODEL_VERSION, unit="cases_per_period", history_end_exclusive=end,
                 horizon=horizon, source_kind=source_kind, limitations=limitations)
    inconsistent = any(
        (stop - start).days != 7 or (index > 0 and ordered[index - 1][1] != start)
        for index, (start, stop, _) in enumerate(ordered)
    )
    if len(ordered) < MIN_ORIGIN or inconsistent or any(
        value is None or not value.is_finite() or value < 0 for _, _, value in ordered
    ):
        limitations.append("Série semanal curta, incompleta ou inconsistente; previsão abstida.")
        return ForecastResult(**scope, method="abstained", status="abstained", points=[],
                              interval_description=None, backtest=None, usable_for_planning=False)

    values = [value for _, _, value in ordered]
    holdout_start = len(values) - weeks + 1 - HOLDOUT_ORIGINS
    holdout = range(holdout_start, len(values) - weeks + 1)
    calibration = range(MIN_ORIGIN, holdout_start - weeks + 1)
    candidates = {"moving_median_4": None, "seasonal_naive_13": 13, "seasonal_naive_52": 52}
    # Compare only origins where every candidate under consideration has historical support.
    available = {name: lag for name, lag in candidates.items()
                 if lag is None or holdout_start - weeks + 1 - lag >= MIN_CALIBRATION}
    shared_calibration = range(max(MIN_ORIGIN, max(lag or 0 for lag in available.values())), calibration.stop)
    method = "moving_median_4"
    if len(shared_calibration) >= MIN_CALIBRATION:
        method = min(available, key=lambda name: sum(
            abs(error) for row in _errors(values, shared_calibration, weeks, available[name]) for error in row
        ))
    lag = available[method]
    forecasts = _predict(values, weeks, lag)
    recent = median(values[-4:])
    prior = median(values[-8:-4])
    drift = abs(recent - prior) > Decimal("0.5") * max(prior, Decimal(1))
    quantiles = [None] * weeks
    coverages = []
    pinball_loss = []
    width = None
    simultaneous_coverage = None
    if len(calibration) >= MIN_CALIBRATION and not drift:
        origins = range(max(calibration.start, lag or 0), calibration.stop)
        calibration_errors = _errors(values, origins, weeks, lag)
        holdout_errors = _errors(values, holdout, weeks, lag)
        for lead, residuals in enumerate(zip(*calibration_errors)):
            low, mid, high = (_quantile(residuals, level) for level in LEVELS)
            pairs = [(values[origin + lead] - errors[lead], values[origin + lead])
                     for origin, errors in zip(holdout, holdout_errors)]
            below = sum(actual < _positive(estimate + low) for estimate, actual in pairs)
            above = sum(actual > _positive(estimate + high) for estimate, actual in pairs)
            coverage = (len(holdout) - below - above) / len(holdout)
            coverages.append(coverage)
            pinball_loss.append([
                float(sum(max(level * error, (level - 1) * error) for estimate, actual in pairs
                          for error in [actual - _positive(estimate + correction)]) / len(pairs))
                for level, correction in zip(LEVELS, (low, mid, high))
            ])
            # With eight origins the observed frequency is coarse. Reject intervals
            # missing more than two outcomes in either tail or more than three overall.
            if below <= 2 and above <= 2 and coverage >= 0.625:
                quantiles[lead] = tuple(float(_positive(forecasts[lead] + error)) for error in (low, mid, high))
        worst = sorted(max(map(abs, errors)) for errors in calibration_errors)
        rank = (9 * (len(worst) + 1) + 9) // 10
        if rank <= len(worst):
            candidate = worst[rank - 1]
            simultaneous_coverage = sum(max(map(abs, errors)) <= candidate for errors in holdout_errors) / len(holdout)
            if simultaneous_coverage >= 0.875:
                width = candidate

    scored_origins = holdout if holdout_start >= MIN_ORIGIN else range(MIN_ORIGIN, len(values))
    comparison_weeks = weeks if holdout_start >= MIN_ORIGIN else 1
    actuals = [v for origin in scored_origins for v in values[origin:origin + comparison_weeks]]
    comparison = {
        name: _metrics([e for row in _errors(values, scored_origins, comparison_weeks, model_lag) for e in row], actuals)
        for name, model_lag in candidates.items()
        if model_lag is None or scored_origins.start >= model_lag
    }
    metrics = comparison[method]
    calibrated = metrics["wape"] is not None and all(quantiles)
    if not calibrated:
        quantiles = [None] * weeks
        limitations.append("Percentis omitidos por histórico, mudança de regime ou cobertura insuficiente na avaliação.")
    if drift:
        limitations.append("Mudança recente de nível superior a 50%; estimativas diagnósticas excluídas do planejamento.")
    if metrics["wape"] is None:
        limitations.append("WAPE indisponível quando os realizados somam zero ou não há backtest.")
    if not any(name.startswith("seasonal") for name in comparison):
        limitations.append("Sem histórico anterior suficiente para comparar um baseline sazonal.")
    limitations.append("Coberturas empíricas de origens semanais sobrepostas, com oito origens de avaliação.")

    points = []
    for lead, estimate in enumerate(forecasts):
        start = end + timedelta(weeks=lead)
        p10, p50, p90 = quantiles[lead] or (None, None, None)
        points.append(ForecastPoint(
            period=Period(start=start, end_exclusive=start + timedelta(weeks=1), timezone=timezone),
            point_estimate=float(estimate), lower=None if width is None else float(_positive(estimate - width)),
            upper=None if width is None else float(estimate + width), p10=p10, p50=p50, p90=p90,
        ))
    backtest = Backtest(
        method=method, evaluated_through=end - timedelta(days=1), **metrics,
        limitations=limitations, benchmarks=comparison, quantile_coverage=coverages,
        quantile_pinball_loss=pinball_loss,
        simultaneous_coverage=simultaneous_coverage, evaluation_origins=len(scored_origins),
        calibration_through=ordered[holdout_start - 1][1] if len(calibration) >= MIN_CALIBRATION else None,
        evaluation_starts=ordered[scored_origins.start][0],
    ) if actuals else None
    return ForecastResult(
        **scope, method=method, status="calibrated" if calibrated else "uncalibrated", points=points,
        usable_for_planning=not drift,
        interval_description=(f"Faixa empírica conjunta, cobertura observada de {simultaneous_coverage:.0%}."
                              if width is not None else None),
        backtest=backtest,
    )
