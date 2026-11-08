"""Scoped repository; callers must obtain scope from a trusted principal."""
from dataclasses import dataclass
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.app.data.models import DataSnapshot
from backend.app.data.schemas import SnapshotData

@dataclass(frozen=True)
class DataScope:
    tenant_id: str
    team_ids: frozenset[str]

class ForbiddenScope(Exception):
    pass

def require_team(scope: DataScope, team_id: str):
    if not scope.tenant_id or team_id not in scope.team_ids:
        raise ForbiddenScope()

class DataRepository:
    def __init__(self, session: Session, scope: DataScope):
        self.session, self.scope = session, scope

    def add_snapshot(self, data: SnapshotData):
        c = data.capacity
        require_team(self.scope, c.team_id)
        if c.tenant_id != self.scope.tenant_id:
            raise ForbiddenScope()
        row = DataSnapshot(tenant_id=c.tenant_id, team_id=c.team_id, snapshot_id=c.data_snapshot_id, payload=data.model_dump(mode='json'))
        self.session.add(row)
        self.session.flush()
        return row

    def get_snapshot(self, team_id: str, snapshot_id: str):
        require_team(self.scope, team_id)
        row = self.session.scalar(select(DataSnapshot).where(DataSnapshot.tenant_id == self.scope.tenant_id, DataSnapshot.team_id == team_id, DataSnapshot.snapshot_id == snapshot_id))
        return SnapshotData.model_validate_json(__import__('json').dumps(row.payload)) if row else None

    def list_snapshots(self, team_id: str):
        require_team(self.scope, team_id)
        return list(self.session.scalars(select(DataSnapshot).where(DataSnapshot.tenant_id == self.scope.tenant_id, DataSnapshot.team_id == team_id).order_by(DataSnapshot.id)))

    def list_teams(self):
        rows = self.session.scalars(select(DataSnapshot).where(DataSnapshot.tenant_id == self.scope.tenant_id, DataSnapshot.team_id.in_(self.scope.team_ids)).order_by(DataSnapshot.id))
        return list({row.team_id: row.payload['team'] for row in rows}.values())
