"""Audit read API. Tenant and team scope come only from the verified principal."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.app.audit.log import InvalidCursor, MAX_LIMIT, as_utc, query_events, record_event
from backend.app.audit.tracing import TRACE_ID_PATTERN, normalize_trace_id
from backend.app.auth.dependencies import get_principal
from backend.app.auth.permissions import Permission, Principal
from backend.app.core.ids import ID_PATTERN

router = APIRouter(prefix="/api", tags=["audit"])
FILTERS = ("trace_id", "action", "resource_type", "resource_id", "team_id", "since", "until", "cursor")


def session(request: Request):
    with request.app.state.session_factory() as s:
        yield s


def _item(e):
    return {"id": e.id, "occurred_at": as_utc(e.occurred_at).isoformat(), "trace_id": e.trace_id, "team_id": e.team_id,
            "actor_type": e.actor_type, "actor_user_id": e.actor_user_id, "action": e.action, "outcome": e.outcome,
            "resource_type": e.resource_type, "resource_id": e.resource_id, "details": e.details}


@router.get("/audit")
def list_audit(trace_id: str | None = Query(None, pattern=TRACE_ID_PATTERN.pattern),
               action: str | None = Query(None, max_length=64),
               resource_type: str | None = Query(None, max_length=64),
               resource_id: str | None = Query(None, pattern=ID_PATTERN),
               team_id: str | None = Query(None, pattern=ID_PATTERN),
               since: datetime | None = None, until: datetime | None = None,
               limit: int = Query(100, ge=1, le=MAX_LIMIT), cursor: str | None = Query(None, max_length=512),
               principal: Principal = Depends(get_principal), db=Depends(session)):
    if trace_id is not None:
        trace_id = normalize_trace_id(trace_id)  # accepts dashed or upper case; all-zero id is rejected
        if trace_id is None:
            raise HTTPException(status_code=422, detail={"code": "INVALID_TRACE_ID", "message": "Invalid trace_id"})
    values = dict(trace_id=trace_id, action=action, resource_type=resource_type, resource_id=resource_id,
                  team_id=team_id, since=since, until=until, cursor=cursor)
    used = [k for k in FILTERS if values[k] is not None]  # filter names only, never values

    def audit(outcome, team=None, count=None):
        details = {"filters": used} if count is None else {"filters": used, "result_count": count}
        record_event(db, action="audit.read", outcome=outcome, tenant_id=principal.tenant_id,
                     actor_user_id=principal.user_id, team_id=team, resource_type="audit_events", details=details)
        db.commit()

    def deny():
        audit("denied")
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN_SCOPE", "message": "Scope denied"})

    perm = Permission.AUDIT_READ
    if not principal.has(perm):
        deny()
    if principal.tenant_wide(perm):
        teams = None if team_id is None else frozenset({team_id})
    else:
        allowed = principal.team_ids(perm)
        if team_id is not None and team_id not in allowed:
            deny()
        teams = allowed if team_id is None else frozenset({team_id})
    try:
        events, next_cursor = query_events(db, tenant_id=principal.tenant_id, team_ids=teams, trace_id=trace_id,
                                           action=action, resource_type=resource_type, resource_id=resource_id,
                                           since=since, until=until, limit=limit, cursor=cursor)
    except InvalidCursor:
        raise HTTPException(status_code=422, detail={"code": "INVALID_CURSOR", "message": "Invalid cursor"})
    items = [_item(e) for e in events]
    # A filter value is caller input: store it as the event team only when a
    # membership grants that exact team, never an unverified string.
    audit("success", team_id if team_id in principal.team_ids(perm) else None, len(items))
    return {"items": items, "next_cursor": next_cursor}
