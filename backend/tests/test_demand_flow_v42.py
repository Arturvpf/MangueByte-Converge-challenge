"""Demand flow ingestion: ledgers are reconciled and not double-counted."""
from backend.app.ingestion.csvparse import parse_csv


BASE = ["skill_id", "shift_id", "pool_id", "eligible_hours", "available_hours",
        "period_start", "period_end_exclusive", "timezone", "demand_cases",
        "hours_unit", "demand_unit"]
FLOW = ["incoming_cases", "completed_cases", "cancelled_cases", "reopened_cases",
        "unmet_cases", "backlog_start", "backlog_end"]


def csv(rows, *, flow=True):
    header = BASE + (FLOW if flow else [])
    return ",".join(header) + "\n" + "\n".join(",".join(str(row.get(field, "")) for field in header) for row in rows) + "\n"


def row(**changes):
    value = {
        "skill_id": "helpdesk", "shift_id": "morning", "pool_id": "pool-a",
        "eligible_hours": "30", "available_hours": "30",
        "period_start": "2026-11-02", "period_end_exclusive": "2026-11-09",
        "timezone": "America/Recife", "demand_cases": "129",
        "hours_unit": "hours_per_period", "demand_unit": "cases_per_period",
        "incoming_cases": "120", "completed_cases": "95", "cancelled_cases": "5",
        "reopened_cases": "3", "unmet_cases": "9", "backlog_start": "15", "backlog_end": "38",
    }
    value.update(changes)
    return value


def parse(content):
    return parse_csv(content, tenant_id="tenant-a", team_id="team-a",
                     snapshot_id="snap-a", reference="sample.csv")


def test_flow_schema_is_explicit_and_conserves_backlog():
    result = parse(csv([row()]))
    assert not result["errors"]
    assert result["history"][0]["demand_semantics"] == "incoming_plus_unmet"
    assert result["history"][0]["quantity"] == "129"
    assert result["history"][0]["backlog_end"] == "38"


def test_invalid_backlog_cannot_create_snapshot():
    result = parse(csv([row(backlog_end="5")]))
    assert result["snapshot"] is None
    assert any(error["code"] == "backlog_mismatch" for error in result["errors"])


def test_same_skill_in_two_shifts_counts_demand_once():
    second = row(shift_id="evening", pool_id="pool-b", eligible_hours="10", available_hours="10")
    result = parse(csv([row(), second]))
    assert not result["errors"]
    assert result["history"][0]["quantity"] == "129"
    assert result["history"][0]["incoming_cases"] == "120"


def test_same_skill_conflicting_duplicate_is_rejected():
    result = parse(csv([row(), row(shift_id="evening", pool_id="pool-b",
                                  incoming_cases="121")]))
    assert any(error["code"] == "conflicting_demand_flow" for error in result["errors"])


def test_legacy_data_is_not_mislabeled_as_verified_arrivals():
    legacy = {field: value for field, value in row().items() if field not in FLOW}
    result = parse(csv([legacy], flow=False))
    assert not result["errors"]
    assert result["history"][0]["demand_semantics"] == "legacy_unclassified"
