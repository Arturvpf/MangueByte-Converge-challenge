"""Snapshot metrics. Pool hours are summed once, even when several skills share them."""
from decimal import Decimal

from backend.app.data.schemas import SnapshotData
from backend.app.metrics.engine import homogeneous_metrics, prepare_matrix


def _text(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def summarize(snapshot: SnapshotData) -> dict:
    matrix = prepare_matrix(snapshot.capacity, snapshot.demand)
    known = all(pool.available_hours is not None for pool in matrix.pools)
    pool_hours = sum((pool.available_hours for pool in matrix.pools), Decimal(0)) if known else None
    row_hours = sum((row.eligible_hours for row in matrix.rows if row.eligible_hours is not None), Decimal(0))
    shared = [pool.pool_id for pool in matrix.pools if sum(pool.pool_id in row.pool_ids for row in matrix.rows) > 1]
    limitations = list(matrix.limitations)
    if not known:
        limitations.append("Orçamento de pool desconhecido; hora ausente não foi tratada como zero.")
    if shared:
        limitations.append("Pool compartilhado: as horas não são somadas de novo por skill.")
    return {
        "data_snapshot_id": snapshot.capacity.data_snapshot_id,
        "pool_hours": _text(pool_hours),
        "row_eligible_hours_sum": _text(row_hours),
        "shared_pools": shared,
        "hours_counted_once": True,
        "demand": [{"skill_id": skill, "quantity": _text(quantity)} for skill, quantity in matrix.demand],
        "limitations": limitations,
        "homogeneous": None,
    }


def homogeneous_from(aggregates: dict | None) -> dict | None:
    """Compute only when every aggregate input was supplied. Missing projected demand uses the current demand."""
    if not aggregates:
        return None
    keys = ("headcount", "nominal_hours", "availability", "cases_per_hour", "demand_cases")
    if any(not aggregates.get(key) for key in keys):
        return None
    kwargs = dict(
        headcount=int(aggregates["headcount"]), nominal_hours_per_person=Decimal(aggregates["nominal_hours"]),
        availability=Decimal(aggregates["availability"]), cases_per_hour=Decimal(aggregates["cases_per_hour"]),
        demand_cases=Decimal(aggregates["demand_cases"]),
    )
    if aggregates.get("projected_demand"):
        kwargs["projected_demand_cases"] = Decimal(aggregates["projected_demand"])
    result = homogeneous_metrics(**kwargs)
    return {
        "capacity_cases": _text(result.capacity_cases),
        "ipd": _text(result.ipd),
        "required_headcount": result.required_headcount,
        "headcount_gap": result.headcount_gap,
        "inputs": "agregados do arquivo; não são pessoas identificadas",
    }
