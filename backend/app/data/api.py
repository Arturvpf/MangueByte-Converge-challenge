"""Read-only API. P2-01 must override get_data_scope with verified identity."""
from fastapi import APIRouter, Depends, HTTPException, Request
from backend.app.data.repository import CorruptSnapshot, DataRepository, DataScope, ForbiddenScope
from backend.app.data.schemas import SnapshotData

router = APIRouter(prefix='/api', tags=['data'])

def get_data_scope() -> DataScope:
    raise HTTPException(status_code=403, detail={'code': 'FORBIDDEN_SCOPE', 'message': 'Authorization unavailable'})

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
