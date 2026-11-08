"""Route dependencies. Identity comes only from the bearer token and the database."""
import re

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.audit.log import record_event
from backend.app.audit.tracing import current_trace_id
from backend.app.auth.models import MembershipRow, Tenant, User
from backend.app.auth.permissions import TENANT_WIDE_ROLES, Membership, Permission, Principal, Role
from backend.app.auth.tokens import InvalidToken, verify_token

# Denied path values are attacker-controlled: only id-shaped values reach the audit details.
AUDITABLE_TEAM = re.compile(r"[A-Za-z0-9._~-]{1,128}")


def unauthenticated() -> HTTPException:
    return HTTPException(status_code=401, detail={"code": "UNAUTHENTICATED", "message": "Authentication required"},
                         headers={"WWW-Authenticate": "Bearer"})


def forbidden() -> HTTPException:
    return HTTPException(status_code=403, detail={"code": "FORBIDDEN_SCOPE", "message": "Scope denied"})


def bearer_token(request: Request) -> str:
    values = request.headers.getlist("authorization")
    if len(values) != 1:
        raise unauthenticated()
    scheme, _, token = values[0].partition(" ")
    if scheme.lower() != "bearer" or not token or token != token.strip() or " " in token:
        raise unauthenticated()
    return token


def load_principal(session: Session, claims: dict) -> Principal | None:
    """Principal for verified claims, or None if the account no longer qualifies."""
    user = session.get(User, claims["sub"])
    if user is None or not user.active or user.tenant_id != claims["tid"] or user.token_version != claims["ver"]:
        return None
    tenant = session.get(Tenant, user.tenant_id)
    if tenant is None or not tenant.active:
        return None
    rows = session.scalars(select(MembershipRow).where(MembershipRow.user_id == user.user_id,
                                                       MembershipRow.tenant_id == user.tenant_id)
                           .order_by(MembershipRow.id))
    memberships = []
    for row in rows:
        try:
            role = Role(row.role)
        except ValueError:  # unknown role stored: grants nothing
            continue
        if (row.team_id is None and role not in TENANT_WIDE_ROLES) or (row.team_id is not None and not row.team_id.strip()):
            continue  # invalid stored grant (e.g. tenant-wide gestor): never widen scope
        memberships.append(Membership(role, row.team_id))
    return Principal(user.user_id, user.tenant_id, tuple(memberships))


def get_principal(request: Request) -> Principal:
    token = bearer_token(request)
    try:
        claims = verify_token(request.app.state.settings, token)
    except InvalidToken:
        raise unauthenticated() from None
    with request.app.state.session_factory() as session:
        principal = load_principal(session, claims)
    if principal is None:
        raise unauthenticated()
    request.state.token_version = claims["ver"]  # lets workers re-check revocation (tools.PrincipalBoundary)
    return principal


def deny(request: Request, principal: Principal, permission: Permission, target_team: str | None = None):
    """Audit the denial in its own short transaction, then raise 403.

    The requested team is untrusted input: it never fills audit team_id, and is kept in
    details only when it looks like an identifier (no email or free text).
    """
    details = {"permission": permission.value}
    if isinstance(target_team, str) and AUDITABLE_TEAM.fullmatch(target_team) and "@" not in target_team:
        details["target_team"] = target_team
    with request.app.state.session_factory() as session:
        record_event(session, action="authz.denied", outcome="denied", tenant_id=principal.tenant_id,
                     actor_user_id=principal.user_id, details=details, trace_id=current_trace_id())
        session.commit()
    raise forbidden()


def require_permission(permission: Permission):
    """Permission on at least one team; handlers must still scope by team."""
    def dependency(request: Request, principal: Principal = Depends(get_principal)) -> Principal:
        if not principal.has(permission):
            deny(request, principal, permission)
        return principal
    return dependency


def require_team_permission(permission: Permission):
    """Permission on the {team_id} path parameter within the principal's own tenant.

    Only the path is read, never the query string; a route without {team_id} is a bug.
    """
    def dependency(request: Request, principal: Principal = Depends(get_principal)) -> Principal:
        if "team_id" not in request.path_params:
            raise HTTPException(status_code=500, detail={"code": "MISCONFIGURED_ROUTE",
                                                         "message": "Route has no team_id path parameter"})
        team_id = request.path_params["team_id"]
        if not isinstance(team_id, str) or not team_id or not principal.can(permission, team_id):
            deny(request, principal, permission, team_id)
        return principal
    return dependency


def require_tenant_permission(permission: Permission):
    def dependency(request: Request, principal: Principal = Depends(get_principal)) -> Principal:
        if not principal.tenant_wide(permission):
            deny(request, principal, permission)
        return principal
    return dependency
