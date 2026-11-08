"""Parse an aggregate CSV. A row error keeps the import incomplete."""
import csv
import json
from datetime import date
from decimal import Decimal, InvalidOperation
from io import StringIO

from backend.app.contracts.v1 import Period
from backend.app.data.schemas import SnapshotData

REQUIRED = (
    "skill_id", "shift_id", "pool_id", "eligible_hours", "available_hours", "period_start",
    "period_end_exclusive", "timezone", "demand_cases", "hours_unit", "demand_unit",
)
OPTIONAL = (
    "availability_fraction", "cost_min", "cost_max", "currency", "cases_per_hour", "headcount",
    "nominal_hours", "projected_demand", "skill_name", "shift_name",
)
FORBIDDEN = {
    "salary", "salario", "salário", "cpf", "email", "e-mail", "nome", "name", "person_id",
    "employee_id", "employee", "pessoa", "motivo_afastamento", "absence_reason", "afastamento",
}
AGGREGATE_FIELDS = ("cases_per_hour", "headcount", "nominal_hours", "availability_fraction", "projected_demand")


def _cell(value: str | None) -> str:
    return "" if value is None else value.strip()


def _decimal(value: str):
    if value == "" or any(mark in value for mark in "eE ") or value != value.strip():
        return None
    try:
        number = Decimal(value)
    except InvalidOperation:
        return None
    if not number.is_finite() or number < 0:
        return None
    return number


def _error(line: int, column: str, code: str) -> dict:
    return {"line": line, "column": column, "code": code}


def parse_csv(content: str, *, tenant_id: str, team_id: str, snapshot_id: str, reference: str):
    errors = []
    reader = csv.DictReader(StringIO(content))
    headers = reader.fieldnames or []
    if any(header is None or header.strip() == "" or header != header.strip() for header in headers):
        return _empty(errors + [_error(1, "header", "invalid_header")])
    normalized = [header.casefold() for header in headers]
    if len(normalized) != len(set(normalized)):
        errors.append(_error(1, "header", "duplicate_header"))
    for header in normalized:
        if header in FORBIDDEN:
            errors.append(_error(1, header, "forbidden_column"))
        elif header not in REQUIRED and header not in OPTIONAL:
            errors.append(_error(1, header, "unknown_column"))
    for header in REQUIRED:
        if header not in normalized:
            errors.append(_error(1, header, "missing_column"))
    if errors:
        return _empty(errors)

    canonical = {header.casefold(): header for header in headers}
    rows = []
    for index, raw in enumerate(reader, start=2):
        item = {name: _cell(raw.get(canonical.get(name))) for name in (*REQUIRED, *OPTIONAL)}
        if not any(item.values()):
            continue
        row_errors = _row_errors(index, item)
        errors.extend(row_errors)
        if not row_errors:
            rows.append((index, item))
    if errors or not rows:
        if not rows and not errors:
            errors.append(_error(2, "file", "empty_file"))
        return _empty(errors)
    return _assemble(rows, errors, tenant_id=tenant_id, team_id=team_id, snapshot_id=snapshot_id, reference=reference)


def _row_errors(line: int, item: dict) -> list[dict]:
    found = []
    for column in ("skill_id", "shift_id", "pool_id", "period_start", "period_end_exclusive", "timezone"):
        if not item[column]:
            found.append(_error(line, column, "missing_value"))
    if item["hours_unit"] == "":
        found.append(_error(line, "hours_unit", "missing_unit"))
    elif item["hours_unit"] != "hours_per_period":
        found.append(_error(line, "hours_unit", "incompatible_unit"))
    if item["demand_unit"] == "":
        found.append(_error(line, "demand_unit", "missing_unit"))
    elif item["demand_unit"] != "cases_per_period":
        found.append(_error(line, "demand_unit", "incompatible_unit"))
    for column in ("eligible_hours", "available_hours", "demand_cases"):
        if _decimal(item[column]) is None:
            found.append(_error(line, column, "invalid_number"))
    for column in ("availability_fraction", "cost_min", "cost_max", "cases_per_hour", "nominal_hours", "projected_demand"):
        if item.get(column) not in (None, "") and _decimal(item[column]) is None:
            found.append(_error(line, column, "invalid_number"))
    if item.get("headcount") not in (None, "") and (not item["headcount"].isdigit() or int(item["headcount"]) < 0):
        found.append(_error(line, "headcount", "invalid_number"))
    try:
        start = date.fromisoformat(item["period_start"]) if item["period_start"] else None
        end = date.fromisoformat(item["period_end_exclusive"]) if item["period_end_exclusive"] else None
    except ValueError:
        found.append(_error(line, "period", "invalid_period"))
        start = end = None
    if start and end and end <= start:
        found.append(_error(line, "period", "invalid_period"))
    if item["timezone"]:
        try:
            Period(start=start or date(2026, 1, 1), end_exclusive=end or date(2026, 1, 2), timezone=item["timezone"])
        except ValueError:
            found.append(_error(line, "timezone", "invalid_timezone"))
    if (item.get("cost_min") in (None, "")) != (item.get("cost_max") in (None, "")):
        found.append(_error(line, "cost_min", "invalid_cost"))
    if (item.get("cost_min") not in (None, "")) != (item.get("currency") not in (None, "")):
        found.append(_error(line, "currency", "invalid_cost"))
    if item.get("currency") not in (None, "", "BRL"):
        found.append(_error(line, "currency", "invalid_cost"))
    return found


def _empty(errors):
    return {"errors": errors, "history": [], "aggregates": {}, "snapshot": None}


def _assemble(rows, errors, *, tenant_id, team_id, snapshot_id, reference):
    for column in AGGREGATE_FIELDS:
        values = {item[column] for _, item in rows if item.get(column) not in (None, "")}
        if len(values) > 1:
            errors.append(_error(1, column, "conflicting_aggregate"))
    if errors:
        return _empty(errors)
    last_end = max(item["period_end_exclusive"] for _, item in rows)
    selected = [item for _, item in rows if item["period_end_exclusive"] == last_end]
    pools = {}
    skills = {}
    shifts = {}
    matrix = {}
    demand = {}
    for item in selected:
        pools.setdefault(item["pool_id"], item["available_hours"])
        if pools[item["pool_id"]] != item["available_hours"]:
            errors.append(_error(1, "available_hours", "conflicting_pool"))
        skills.setdefault(item["skill_id"], item.get("skill_name") or item["skill_id"])
        if item.get("skill_name") and skills[item["skill_id"]] != item["skill_name"]:
            errors.append(_error(1, "skill_name", "conflicting_name"))
        shifts.setdefault(item["shift_id"], item.get("shift_name") or item["shift_id"])
        key = (item["skill_id"], item["shift_id"])
        matrix.setdefault(key, {"pools": [], "eligible": item["eligible_hours"], "availability": item.get("availability_fraction") or "",
                                "cost_min": item.get("cost_min") or "", "cost_max": item.get("cost_max") or "", "currency": item.get("currency") or ""})
        if item["pool_id"] not in matrix[key]["pools"]:
            matrix[key]["pools"].append(item["pool_id"])
        if matrix[key]["eligible"] != item["eligible_hours"]:
            errors.append(_error(1, "eligible_hours", "conflicting_row"))
        demand.setdefault(item["skill_id"], item["demand_cases"])
        if demand[item["skill_id"]] != item["demand_cases"]:
            errors.append(_error(1, "demand_cases", "conflicting_demand"))
    if errors:
        return _empty(errors)
    sample = selected[0]
    if any(item["period_start"] != sample["period_start"] or item["timezone"] != sample["timezone"] for item in selected):
        return _empty(errors + [_error(1, "period", "conflicting_period")])
    period = {"start": sample["period_start"], "end_exclusive": sample["period_end_exclusive"], "timezone": sample["timezone"]}
    capacity_rows = []
    for (skill_id, shift_id), row in matrix.items():
        cost_min = row["cost_min"]
        capacity_rows.append({
            "skill_id": skill_id, "shift_id": shift_id, "eligible_hours": float(_decimal(row["eligible"])),
            "pool_ids": row["pools"],
            "availability_fraction": None if row["availability"] == "" else float(_decimal(row["availability"])),
            "cost_min": None if cost_min == "" else float(_decimal(cost_min)),
            "cost_max": None if row["cost_max"] == "" else float(_decimal(row["cost_max"])),
            "currency": row["currency"] or None,
        })
    snapshot = {
        "team": {"id": team_id, "name": team_id},
        "skills": [{"id": key, "name": value} for key, value in sorted(skills.items())],
        "roles": [],
        "shifts": [{"id": key, "name": value} for key, value in sorted(shifts.items())],
        "source": {"kind": "csv", "reference": reference[:200], "version": snapshot_id},
        "capacity": {
            "schema_version": "1.0", "tenant_id": tenant_id, "team_id": team_id, "data_snapshot_id": snapshot_id,
            "period": period, "hours_unit": "hours_per_period",
            "pools": [{"pool_id": key, "available_hours": float(_decimal(value))} for key, value in sorted(pools.items())],
            "rows": capacity_rows,
            "limitations": ["Horas de pool entram uma vez. Arquivo agregado; sem pessoas identificadas."],
        },
        "demand": {
            "schema_version": "1.0", "tenant_id": tenant_id, "team_id": team_id, "data_snapshot_id": snapshot_id,
            "records": [{
                "skill_id": skill, "period": period, "quantity": float(_decimal(quantity)), "unit": "cases_per_period",
            } for skill, quantity in sorted(demand.items())],
            "limitations": ["Demanda agregada do último período do arquivo."],
        },
    }
    SnapshotData.model_validate_json(json.dumps(snapshot))
    history = []
    for end in sorted({item["period_end_exclusive"] for _, item in rows}):
        chunk = [item for _, item in rows if item["period_end_exclusive"] == end]
        history.append({
            "start": chunk[0]["period_start"], "end": end,
            "quantity": str(sum(_decimal(item["demand_cases"]) for item in chunk)),
        })
    first = selected[0]
    aggregates = {
        "cases_per_hour": first.get("cases_per_hour") or None,
        "headcount": first.get("headcount") or None,
        "nominal_hours": first.get("nominal_hours") or None,
        "availability": first.get("availability_fraction") or None,
        "demand_cases": str(sum(_decimal(quantity) for quantity in demand.values())),
        "projected_demand": first.get("projected_demand") or None,
    }
    return {"errors": [], "history": history, "aggregates": aggregates, "snapshot": snapshot}
