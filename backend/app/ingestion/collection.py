"""Collect authorized Jira arrivals without retaining issue content or identities."""
from collections import Counter
import csv
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from io import StringIO
import json
from zoneinfo import ZoneInfo

from sqlalchemy import select, update

from backend.app.data.repository import DataRepository, DataScope
from backend.app.flow.errors import FlowError
from backend.app.flow.models import DataImport, JiraCollection
from backend.app.ingestion.jira import IntegrationUnavailable, fetch_issues
from backend.app.ingestion.service import _guard_team, confirm_import, submit_csv

HISTORY_WEEKS = 88


def _aggregate(issues, skill_map, project, zone, start, end):
    counts = Counter()
    seen = set()
    for issue in issues:
        try:
            identifier = issue["id"]
            if not isinstance(identifier, str) or not identifier:
                raise ValueError
            fields = issue["fields"]
            if fields["project"]["key"].upper() != project.upper():
                raise ValueError
            created = datetime.fromisoformat(fields["created"])
            if created.utcoffset() is None:
                raise ValueError
            created = created.astimezone(zone).date()
            if not start <= created < end or identifier in seen:
                continue
            skill = skill_map[fields["issuetype"]["id"]]
        except (AttributeError, KeyError, TypeError, ValueError):
            raise IntegrationUnavailable("Metadados Jira inválidos ou tipo sem competência autorizada") from None
        seen.add(identifier)
        monday = created - timedelta(days=created.weekday())
        counts[(monday, skill)] += 1
    return counts


def _arrivals_csv(snapshot, counts, start, end, rate):
    from backend.app.ingestion.csvparse import REQUIRED

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=[*REQUIRED, "cases_per_hour", "cost_min", "cost_max", "currency"],
                            lineterminator="\n")
    writer.writeheader()
    pools = {pool.pool_id: pool for pool in snapshot.capacity.pools}
    for index in range((end - start).days // 7):
        monday = start + timedelta(weeks=index)
        for row in sorted(snapshot.capacity.rows, key=lambda row: (row.skill_id, row.shift_id)):
            for pool in sorted(row.pool_ids):
                writer.writerow({
                    "skill_id": row.skill_id, "shift_id": row.shift_id, "pool_id": pool,
                    "eligible_hours": row.eligible_hours, "available_hours": pools[pool].available_hours,
                    "period_start": monday.isoformat(), "period_end_exclusive": (monday + timedelta(weeks=1)).isoformat(),
                    "timezone": snapshot.capacity.period.timezone, "demand_cases": counts[(monday, row.skill_id)],
                    "hours_unit": "hours_per_period", "demand_unit": "cases_per_period",
                    "cases_per_hour": rate, "cost_min": row.cost_min, "cost_max": row.cost_max, "currency": row.currency,
                })
    return buffer.getvalue()


def collect_jira(session, principal, settings, *, transport=None, now=None, min_interval_seconds=0):
    team = settings.jira_team_id
    if not team or not settings.jira_tenant_id or not settings.jira_capacity_snapshot_id:
        raise IntegrationUnavailable("Jira pendente: configure o escopo e a fonte de capacidade")
    if principal.tenant_id != settings.jira_tenant_id:
        raise FlowError(403, "FORBIDDEN_SCOPE")
    _guard_team(principal, team)
    repo = DataRepository(session, DataScope(principal.tenant_id, frozenset({team})))
    capacity = repo.get_snapshot(team, settings.jira_capacity_snapshot_id)
    if (capacity is None or capacity.source.kind in {"synthetic", "jira"}
            or (capacity.capacity.period.end_exclusive - capacity.capacity.period.start).days != 7):
        raise IntegrationUnavailable("Snapshot semanal de capacidade indisponível")
    try:
        skill_map = json.loads(settings.jira_skill_map or "{}")
        if not isinstance(skill_map, dict) or not skill_map:
            raise ValueError
        if not set(skill_map.values()).issubset({row.skill_id for row in capacity.capacity.rows}):
            raise ValueError
    except (ValueError, TypeError):
        raise IntegrationUnavailable("Mapeamento de tipos Jira para competências inválido") from None
    key = sha256(f"{settings.jira_base_url}|{settings.jira_project_key}".encode()).hexdigest()
    identity = (principal.tenant_id, team, key)
    checkpoint = session.get(JiraCollection, identity)
    instant = now or datetime.now(timezone.utc)
    if checkpoint and checkpoint.last_success and min_interval_seconds:
        last = checkpoint.last_success
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if (instant - last).total_seconds() < min_interval_seconds:
            return {"status": "up_to_date", "snapshot_id": checkpoint.snapshot_id, "duplicated": True}
    zone = ZoneInfo(capacity.capacity.period.timezone)
    today = instant.astimezone(zone).date()
    end = today - timedelta(days=today.weekday())
    start = end - timedelta(weeks=HISTORY_WEEKS)
    # Query a boundary buffer, then assign weeks in the snapshot's timezone.
    issues = fetch_issues(settings, transport, created_from=start - timedelta(days=1),
                          created_to=end + timedelta(days=1))
    counts = _aggregate(issues, skill_map, settings.jira_project_key, zone, start, end)
    imported = session.scalar(select(DataImport).where(
        DataImport.tenant_id == principal.tenant_id, DataImport.team_id == team,
        DataImport.snapshot_id == settings.jira_capacity_snapshot_id, DataImport.status == "complete",
    ))
    rate = imported.aggregates.get("cases_per_hour") if imported else None
    content = _arrivals_csv(capacity, counts, start, end, rate)
    if checkpoint is None:
        checkpoint = JiraCollection(tenant_id=identity[0], team_id=team, source_key=key)
        session.add(checkpoint)
        session.flush()
    else:
        session.execute(update(JiraCollection).where(
            JiraCollection.tenant_id == identity[0], JiraCollection.team_id == team,
            JiraCollection.source_key == key,
        ).values(last_success=instant))
        session.refresh(checkpoint)
    row = submit_csv(session, principal, team_id=team, filename=f"jira-arrivals-{key[:16]}.csv",
                     content=content, source_kind="jira")
    duplicate = row.status == "complete"
    if row.status == "invalid":
        raise IntegrationUnavailable("Agregado Jira incompatível com o snapshot de capacidade")
    if not duplicate:
        row.history = [{**week, "demand_semantics": "jira_created_arrivals"} for week in row.history]
        row.preview = {**row.preview, "capacity": {**row.preview["capacity"], "limitations": [
            "Capacidade repetida a partir do snapshot autorizado " + settings.jira_capacity_snapshot_id + ".",
            "Jira fornece chegadas por criação. SLA, reabertura e backlog não foram observados.",
        ]}}
        confirm_import(session, principal, row.import_id)
    checkpoint.snapshot_id = row.snapshot_id
    checkpoint.last_success = instant
    return {"status": "complete", "snapshot_id": row.snapshot_id, "duplicated": duplicate}
