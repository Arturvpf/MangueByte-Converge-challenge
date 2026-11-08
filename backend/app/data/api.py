"""Read-only API. Scope comes from the verified principal (P2-01)."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from backend.app.auth.dependencies import deny, require_permission
from backend.app.auth.permissions import Permission, Principal
from backend.app.data.models import DataSnapshot
from backend.app.flow.models import DataImport

from backend.app.data.repository import CorruptSnapshot, DataRepository, DataScope, ForbiddenScope
from backend.app.data.schemas import SnapshotData

router = APIRouter(prefix='/api', tags=['data'])

def get_data_scope(request: Request, principal: Principal = Depends(require_permission(Permission.DATA_READ))) -> DataScope:
    request.state.data_principal = principal
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

def deny_scope(request: Request):
    # Scope overrides are an internal testing boundary and may not supply a principal.
    principal = getattr(request.state, 'data_principal', None)
    if principal is not None:
        deny(request, principal, Permission.DATA_READ)
    raise HTTPException(status_code=403, detail={'code': 'FORBIDDEN_SCOPE', 'message': 'Scope denied'})

@router.get('/teams/{team_id}/snapshots')
def snapshots(team_id: str, request: Request, repo: DataRepository = Depends(repository)):
    try:
        return [{'snapshot_id': x.snapshot_id, 'created_at': x.created_at, 'source': {'kind': x.source_kind, 'reference': x.source_reference, 'version': x.source_version}} for x in repo.list_snapshots(team_id)]
    except CorruptSnapshot:
        raise HTTPException(status_code=500, detail='Stored snapshot is invalid')
    except ForbiddenScope:
        deny_scope(request)

@router.get('/teams/{team_id}/snapshots/{snapshot_id}', response_model=SnapshotData)
def snapshot(team_id: str, snapshot_id: str, request: Request, repo: DataRepository = Depends(repository)):
    try:
        result = repo.get_snapshot(team_id, snapshot_id)
    except CorruptSnapshot:
        raise HTTPException(status_code=500, detail='Stored snapshot is invalid')
    except ForbiddenScope:
        deny_scope(request)
    if result is None:
        raise HTTPException(status_code=404, detail='Snapshot not found')
    return result


@router.get('/teams/{team_id}/demand-flow')
def demand_flow(team_id: str, snapshot_id: str, request: Request,
                principal: Principal = Depends(require_permission(Permission.DATA_READ))):
    """Read-only aggregate demand ledger; never identifies employees or ticket authors.

    Legacy imports cannot be represented as verified arrivals/backlog, and the
    response explicitly labels their semantics as unclassified.
    """
    if not principal.can(Permission.DATA_READ, team_id):
        raise HTTPException(status_code=404, detail={'code': 'NOT_FOUND'})
    with request.app.state.session_factory() as session:
        row = session.scalar(select(DataImport).where(
            DataImport.tenant_id == principal.tenant_id, DataImport.team_id == team_id,
            DataImport.snapshot_id == snapshot_id, DataImport.status == 'complete',
        ))
        if row is None:
            raise HTTPException(status_code=404, detail={'code': 'NOT_FOUND'})
        entries = row.history or []
        return {
            'team_id': team_id, 'snapshot_id': snapshot_id, 'source_kind': row.source_kind,
            'items': entries,
            'limitations': (['Fluxo apenas agregado; sem avaliação de pessoas.'] +
                (['Campos legados não comprovam entradas ou demanda latente.']
                 if any(item.get('demand_semantics') != 'incoming_plus_unmet' for item in entries)
                 else [])),
        }
