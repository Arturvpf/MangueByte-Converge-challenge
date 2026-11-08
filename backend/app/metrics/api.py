"""Metrics for one snapshot. Shared pool hours are counted once."""
from uuid import uuid4
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from backend.app.auth.dependencies import deny, require_team_permission
from backend.app.auth.permissions import Permission, Principal
from backend.app.data.repository import DataRepository, DataScope
from backend.app.flow.errors import FlowError
from backend.app.flow.models import DataImport, MetricResult
from backend.app.metrics.engine import MetricsError
from backend.app.metrics.summary import homogeneous_from, summarize

router = APIRouter(prefix="/api", tags=["metrics"])


def _call(request, principal, fn):
    try:
        with request.app.state.session_factory() as session:
            result = fn(session)
            session.commit()
            return result
    except FlowError as exc:
        if exc.status == 403:
            deny(request, principal, Permission.DATA_READ, exc.team_id)
        raise HTTPException(status_code=exc.status, detail={"code": exc.code, "message": exc.code}) from None
    except MetricsError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code.value, "message": exc.code.value}) from None


@router.get("/teams/{team_id}/metrics")
def metrics(team_id: str, snapshot_id: str, request: Request,
            principal: Principal = Depends(require_team_permission(Permission.DATA_READ))):
    def run(session):
        data = DataRepository(session, DataScope(principal.tenant_id, frozenset({team_id}))).get_snapshot(team_id, snapshot_id)
        if data is None:
            raise FlowError(404, "NOT_FOUND", team_id)
        existing = session.scalar(select(MetricResult).where(
            MetricResult.tenant_id == principal.tenant_id, MetricResult.team_id == team_id,
            MetricResult.snapshot_id == snapshot_id,
        ))
        if existing is not None:
            return {"metric_id": existing.metric_id, **existing.payload}
        summary = summarize(data)
        imported = session.scalar(select(DataImport).where(
            DataImport.tenant_id == principal.tenant_id, DataImport.snapshot_id == snapshot_id,
        ))
        summary["homogeneous"] = homogeneous_from(imported.aggregates if imported else None)
        row = MetricResult(
            metric_id=str(uuid4()), tenant_id=principal.tenant_id, team_id=team_id, snapshot_id=snapshot_id,
            payload=summary, created_at=datetime.now(timezone.utc),
        )
        session.add(row)
        session.flush()
        return {"metric_id": row.metric_id, **summary}
    return _call(request, principal, run)
