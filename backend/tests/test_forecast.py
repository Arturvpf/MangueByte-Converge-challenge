"""Short history abstains. The backtest cannot see the point it is scoring."""
from datetime import date, timedelta
from decimal import Decimal

from backend.app.forecast.engine import NOT_A_PERCENTILE, forecast_series, predict_next


def weeks(quantities):
    start = date(2026, 1, 5)
    points = []
    for index, quantity in enumerate(quantities):
        opening = start + timedelta(days=7 * index)
        points.append((opening, opening + timedelta(days=7), None if quantity is None else Decimal(quantity)))
    return points


def test_short_history_abstains_without_percentiles():
    result = forecast_series(
        tenant_id="tenant-demo-a", team_id="team-aurora", data_snapshot_id="snap-1",
        timezone="America/Fortaleza", observations=weeks([10, 12, None]),
    )
    assert result.status == "abstained" and result.points == []
    text = result.model_dump_json()
    assert NOT_A_PERCENTILE in result.limitations
    assert '"P10"' not in text and '"P50"' not in text and '"P90"' not in text


def test_backtest_does_not_see_the_future_point():
    series = [10] * 8 + [100]
    assert predict_next([Decimal(10)] * 8) == Decimal(10)
    result = forecast_series(
        tenant_id="tenant-demo-a", team_id="team-aurora", data_snapshot_id="snap-1",
        timezone="America/Fortaleza", observations=weeks(series),
    )
    assert result.status == "uncalibrated"
    assert result.backtest is not None and result.backtest.mae == 90
    assert result.interval_description is None
    assert all(point.lower is None and point.upper is None for point in result.points)
    assert "P10" not in result.method and "P50" not in result.method and "P90" not in result.method


def test_multiple_rolling_origins_required_before_calibration():
    result = forecast_series(
        tenant_id="tenant-demo-a", team_id="team-aurora", data_snapshot_id="snap-1",
        timezone="America/Fortaleza", observations=weeks([10] * 12),
    )
    assert result.status == "uncalibrated"
    assert result.backtest is not None

def test_long_stable_weekly_history_has_tested_empirical_interval():
    result = forecast_series(
        tenant_id="tenant-demo-a", team_id="team-aurora", data_snapshot_id="snap-long",
        timezone="America/Fortaleza", observations=weeks([10] * 40),
    )
    assert result.status == "calibrated"
    assert result.interval_description is not None
    assert all(p.lower == 10 and p.upper == 10 for p in result.points)


def test_gap_in_weekly_history_abstains_even_with_long_series():
    rows = weeks([10] * 28)
    shifted = [(start + timedelta(days=7), end + timedelta(days=7), value) for start, end, value in rows[12:]]
    result = forecast_series(
        tenant_id="tenant-demo-a", team_id="team-aurora", data_snapshot_id="snap-bad",
        timezone="America/Fortaleza", observations=rows[:12] + shifted,
    )
    assert result.status == "abstained"


def test_28_weeks_cannot_validate_four_week_simultaneous_interval():
    result = forecast_series(
        tenant_id="tenant-demo-a", team_id="team-aurora", data_snapshot_id="short-horizon",
        timezone="America/Fortaleza", observations=weeks([10] * 28),
    )
    assert result.status == "uncalibrated"
    assert result.interval_description is None


def test_drift_in_holdout_blocks_empirical_calibration():
    result = forecast_series(
        tenant_id="tenant-demo-a", team_id="team-aurora", data_snapshot_id="drift",
        timezone="America/Fortaleza", observations=weeks([10] * 31 + [40] * 9),
    )
    assert result.status == "uncalibrated"
    assert result.interval_description is None
