"""Read-only API. Scope comes from the verified principal (P2-01)."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from backend.app.auth.dependencies import require_permission
from backend.app.auth.permissions import Permission, Principal
from backend.app.data.models import DataSnapshot
from backend.app.data.repository import CorruptSnapshot, DataRepository, DataScope, ForbiddenScope
from backend.app.data.schemas import SnapshotData

router = APIRouter(prefix='/api', tags=['data'])

def get_data_scope(request: Request, principal: Principal = Depends(require_permission(Permission.DATA_READ))) -> DataScope:
    team_ids = set(principal.team_ids(Permission.DATA_READ))
    if principal.tenant_wide(Permission.DATA_READ):
        with request.app.state.session_factory() as session:
            team_ids.update(session.scalars(select(DataSnapshot.team_id).where(DataSnapshot.tenant_id == principal.tenant_id).distinct()))
    return DataScope(principal.tenant_id, frozenset(team_ids))

def repository(request: Request, scope: DataScope = Depends(get_data_scope)):
    with request.app.state.session_factory() as session:
        yield DataRepository(session, scope)

@router.get('/teams')
def teams(repo: DataRepository = Depends(repository)):
    try:
        return repo.list_teams()
    except CorruptSnapshot:
        raise HTTPException(status_code=500, detail='Stored snapshot is invalid')

@router.get('/teams/{team_id}/snapshots')
def snapshots(team_id: str, repo: DataRepository = Depends(repository)):
    try:
        return [{'snapshot_id': x.snapshot_id, 'created_at': x.created_at, 'source': {'kind': x.source_kind, 'reference': x.source_reference, 'version': x.source_version}} for x in repo.list_snapshots(team_id)]
    except CorruptSnapshot:
        raise HTTPException(status_code=500, detail='Stored snapshot is invalid')
    except ForbiddenScope:
        raise HTTPException(status_code=403, detail={'code': 'FORBIDDEN_SCOPE', 'message': 'Scope denied'})

@router.get('/teams/{team_id}/snapshots/{snapshot_id}', response_model=SnapshotData)
def snapshot(team_id: str, snapshot_id: str, repo: DataRepository = Depends(repository)):
    try:
        result = repo.get_snapshot(team_id, snapshot_id)
    except CorruptSnapshot:
        raise HTTPException(status_code=500, detail='Stored snapshot is invalid')
    except ForbiddenScope:
        raise HTTPException(status_code=403, detail={'code': 'FORBIDDEN_SCOPE', 'message': 'Scope denied'})
    if result is None:
        raise HTTPException(status_code=404, detail='Snapshot not found')
    return result
