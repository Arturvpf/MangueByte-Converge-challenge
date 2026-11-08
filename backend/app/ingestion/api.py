"""Import endpoints. Tenant comes from the principal."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field

from backend.app.auth.dependencies import deny, require_permission
from backend.app.auth.permissions import Permission, Principal
from backend.app.contracts.v1 import Contract
from backend.app.flow.errors import FlowError
from backend.app.ingestion.jira import IntegrationUnavailable, fetch_issues
from backend.app.ingestion.service import confirm_import, import_jira_fixture, public_import, submit_csv

router = APIRouter(prefix="/api/imports", tags=["imports"])
runner = require_permission(Permission.INVESTIGATION_RUN)


class ImportIn(Contract):
    team_id: str = Field(min_length=1, max_length=128)
    filename: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=200000)


class JiraIn(Contract):
    team_id: str = Field(min_length=1, max_length=128)
    fixture: Literal["issues"]


def _call(request: Request, principal: Principal, permission: Permission, fn):
    try:
        with request.app.state.session_factory() as session:
            result = fn(session)
            session.commit()
            return result
    except FlowError as exc:
        if exc.status == 403:
            deny(request, principal, permission, exc.team_id)
        raise HTTPException(status_code=exc.status, detail={"code": exc.code, "message": exc.code}) from None


@router.post("")
def create_import(body: ImportIn, request: Request, principal: Principal = Depends(runner)):
    return _call(request, principal, Permission.INVESTIGATION_RUN,
                 lambda session: public_import(submit_csv(session, principal, team_id=body.team_id, filename=body.filename, content=body.content)))


@router.get("/{import_id}")
def read_import(import_id: str, request: Request, principal: Principal = Depends(runner)):
    def run(session):
        from backend.app.flow.models import DataImport
        row = session.get(DataImport, import_id)
        if row is None or row.tenant_id != principal.tenant_id:
            raise FlowError(404, "NOT_FOUND")
        if not principal.can(Permission.INVESTIGATION_RUN, row.team_id):
            raise FlowError(403, "FORBIDDEN_SCOPE", row.team_id)
        return public_import(row)
    return _call(request, principal, Permission.INVESTIGATION_RUN, run)


@router.post("/{import_id}/confirm")
def confirm(import_id: str, request: Request, principal: Principal = Depends(runner)):
    return _call(request, principal, Permission.INVESTIGATION_RUN,
                 lambda session: public_import(confirm_import(session, principal, import_id)))


@router.post("/jira")
def jira_fixture(body: JiraIn, request: Request, principal: Principal = Depends(runner)):
    return _call(request, principal, Permission.INVESTIGATION_RUN,
                 lambda session: import_jira_fixture(session, principal, body.team_id))


@router.post("/jira/sync")
def jira_sync(request: Request, principal: Principal = Depends(runner)):
    try:
        fetch_issues(request.app.state.settings)
    except IntegrationUnavailable as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code, "message": str(exc)}) from None
    raise HTTPException(status_code=503, detail={"code": "INTEGRATION_UNAVAILABLE", "message": "validação real do Jira continua pendente"})
