"""Scoped repository; callers must obtain scope from a trusted principal."""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.app.data.models import DataSnapshot
from backend.app.data.schemas import SnapshotData

@dataclass(frozen=True)
class DataScope:
    tenant_id: str
    team_ids: frozenset[str]

@dataclass(frozen=True)
class SnapshotSummary:
    snapshot_id: str
    created_at: datetime
    source_kind: str
    source_reference: str
    source_version: str

class ForbiddenScope(Exception):
    pass

class CorruptSnapshot(Exception):
    pass

def require_team(scope: DataScope, team_id: str):
    if not scope.tenant_id or team_id not in scope.team_ids:
        raise ForbiddenScope()

def checked_payload(row: DataSnapshot) -> SnapshotData:
    try:
        data = SnapshotData.model_validate_json(json.dumps(row.payload))
        c = data.capacity
        if (row.tenant_id, row.team_id, row.snapshot_id) != (c.tenant_id, c.team_id, c.data_snapshot_id):
            raise ValueError('row and payload scope differ')
        return data
    except (ValueError, TypeError):
        raise CorruptSnapshot() from None

class DataRepository:
    def __init__(self, session: Session, scope: DataScope):
        self.session, self.scope = session, scope

    def add_snapshot(self, data: SnapshotData) -> None:
        # Models are mutable: serialize and validate afresh before trusting any field.
        data = SnapshotData.model_validate_json(json.dumps(data.model_dump(mode='json'), allow_nan=False))
        c = data.capacity
        require_team(self.scope, c.team_id)
        if c.tenant_id != self.scope.tenant_id:
            raise ForbiddenScope()
        self.session.add(DataSnapshot(tenant_id=c.tenant_id, team_id=c.team_id, snapshot_id=c.data_snapshot_id, payload=data.model_dump(mode='json')))
        self.session.flush()

    def get_snapshot(self, team_id: str, snapshot_id: str):
        require_team(self.scope, team_id)
        row = self.session.scalar(select(DataSnapshot).where(DataSnapshot.tenant_id == self.scope.tenant_id, DataSnapshot.team_id == team_id, DataSnapshot.snapshot_id == snapshot_id))
        return checked_payload(row) if row else None

    def list_snapshots(self, team_id: str):
        require_team(self.scope, team_id)
        rows = self.session.scalars(select(DataSnapshot).where(DataSnapshot.tenant_id == self.scope.tenant_id, DataSnapshot.team_id == team_id).order_by(DataSnapshot.id))
        result = []
        for row in rows:
            data = checked_payload(row)
            created_at = row.created_at
            created_at = created_at.replace(tzinfo=timezone.utc) if created_at.tzinfo is None else created_at.astimezone(timezone.utc)
            result.append(SnapshotSummary(row.snapshot_id, created_at, data.source.kind, data.source.reference, data.source.version))
        return tuple(result)

    def list_teams(self):
        rows = self.session.scalars(select(DataSnapshot).where(DataSnapshot.tenant_id == self.scope.tenant_id, DataSnapshot.team_id.in_(self.scope.team_ids)).order_by(DataSnapshot.id))
        teams = {}
        for row in rows:
            data = checked_payload(row)
            teams[row.team_id] = data.team
        return list(teams.values())
