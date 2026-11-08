"""Create imports and snapshots. The company comes from the principal."""
import csv
import json
from datetime import datetime, timezone
from hashlib import sha256
from io import StringIO
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.audit.log import record_event
from backend.app.auth.permissions import Permission, Principal
from backend.app.core.ids import valid_id
from backend.app.data.repository import DataRepository, DataScope
from backend.app.data.schemas import SnapshotData
from backend.app.flow.errors import FlowError
from backend.app.flow.models import DataImport, JiraCheckpoint
from backend.app.ingestion.csvparse import REQUIRED, parse_csv
from backend.app.ingestion.jira import load_fixture

COLUMNS = (*REQUIRED, "cases_per_hour")


def _audit(session, principal, action, resource_id, team_id, **details):
    record_event(
        session, action=action, outcome="success", tenant_id=principal.tenant_id, actor_user_id=principal.user_id,
        team_id=team_id, resource_type="import", resource_id=resource_id, details=details,
    )


def _guard_team(principal: Principal, team_id: str) -> None:
    if not valid_id(team_id) or not principal.can(Permission.INVESTIGATION_RUN, team_id):
        raise FlowError(403, "FORBIDDEN_SCOPE", team_id)


def submit_csv(session: Session, principal: Principal, *, team_id: str, filename: str, content: str) -> DataImport:
    _guard_team(principal, team_id)
    if not isinstance(content, str) or not content or len(content) > 200_000:
        raise FlowError(422, "INVALID_IMPORT")
    if not isinstance(filename, str) or not filename.strip() or filename != filename.strip() or len(filename) > 200 or "\n" in filename:
        raise FlowError(422, "INVALID_IMPORT")
    digest = sha256(content.encode()).hexdigest()
    existing = session.scalar(select(DataImport).where(
        DataImport.tenant_id == principal.tenant_id, DataImport.team_id == team_id, DataImport.content_hash == digest,
    ))
    if existing is not None:
        return existing
    parsed = parse_csv(
        content, tenant_id=principal.tenant_id, team_id=team_id, snapshot_id=f"csv-{digest[:20]}", reference=filename,
    )
    row = DataImport(
        import_id=str(uuid4()), tenant_id=principal.tenant_id, team_id=team_id, created_by=principal.user_id,
        status="invalid" if parsed["errors"] else "ready", content_hash=digest, source_kind="csv",
        source_reference=filename, snapshot_id=None, errors=parsed["errors"], history=parsed["history"],
        aggregates=parsed["aggregates"], preview=parsed["snapshot"] or {}, line_count=max(content.count("\n"), 1),
        created_at=datetime.now(timezone.utc),
    )
    session.add(row)
    _audit(session, principal, "import.submit", row.import_id, team_id, status=row.status, lines=row.line_count)
    session.flush()
    return row


def confirm_import(session: Session, principal: Principal, import_id: str) -> DataImport:
    row = session.get(DataImport, import_id)
    if row is None or row.tenant_id != principal.tenant_id:
        raise FlowError(404, "NOT_FOUND")
    _guard_team(principal, row.team_id)
    if row.status == "invalid":
        raise FlowError(409, "IMPORT_INCOMPLETE")
    if row.status == "complete":
        return row
    data = SnapshotData.model_validate_json(json.dumps(row.preview))
    if data.capacity.tenant_id != principal.tenant_id or data.team.id != row.team_id:
        raise FlowError(403, "FORBIDDEN_SCOPE", row.team_id)
    DataRepository(session, DataScope(principal.tenant_id, frozenset({row.team_id}))).add_snapshot(data)
    row.status = "complete"
    row.snapshot_id = data.capacity.data_snapshot_id
    _audit(session, principal, "import.confirm", row.import_id, row.team_id, status="complete")
    session.flush()
    return row


def public_import(row: DataImport) -> dict:
    return {
        "import_id": row.import_id, "team_id": row.team_id, "status": row.status, "source_kind": row.source_kind,
        "source_reference": row.source_reference, "snapshot_id": row.snapshot_id, "errors": row.errors,
        "line_count": row.line_count, "complete": row.status == "complete",
    }


def import_jira_fixture(session: Session, principal: Principal, team_id: str) -> dict:
    _guard_team(principal, team_id)
    document = load_fixture("issues")
    issues = document["issues"]
    known = set(session.scalars(select(JiraCheckpoint.issue_id).where(
        JiraCheckpoint.tenant_id == principal.tenant_id, JiraCheckpoint.issue_id.in_([item["id"] for item in issues]),
    )))
    if known and known >= {item["id"] for item in issues}:
        snapshot_id = session.scalar(select(JiraCheckpoint.snapshot_id).where(
            JiraCheckpoint.tenant_id == principal.tenant_id, JiraCheckpoint.issue_id == next(iter(known)),
        ))
        return {"duplicated": True, "snapshot_id": snapshot_id, "import_id": None, "status": "complete"}
    fresh = [item for item in issues if item["id"] not in known]
    content = _issues_csv(fresh)
    row = submit_csv(session, principal, team_id=team_id, filename="jira-fixture-issues.csv", content=content)
    if row.status != "ready":
        raise FlowError(422, "INVALID_IMPORT")
    row.source_kind = "jira"
    row.preview = {**row.preview, "source": {**row.preview["source"], "kind": "jira"}}
    row = confirm_import(session, principal, row.import_id)
    for item in fresh:
        session.add(JiraCheckpoint(tenant_id=principal.tenant_id, issue_id=item["id"], snapshot_id=row.snapshot_id))
    session.flush()
    return {"duplicated": False, "snapshot_id": row.snapshot_id, "import_id": row.import_id, "status": row.status}


def _issues_csv(issues: list[dict]) -> str:
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(COLUMNS), lineterminator="\n")
    writer.writeheader()
    for issue in issues:
        writer.writerow({column: issue.get(column, "") for column in COLUMNS})
    return buffer.getvalue()


def checkpoint_count(session: Session, tenant_id: str) -> int:
    return session.scalar(select(func.count()).select_from(JiraCheckpoint).where(JiraCheckpoint.tenant_id == tenant_id)) or 0
