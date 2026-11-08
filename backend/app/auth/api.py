"""Login/session routes and tenant user administration. Tenant always comes from the principal."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from backend.app.audit.log import record_event
from backend.app.audit.tracing import current_trace_id
from backend.app.auth.dependencies import deny, get_principal, require_tenant_permission, unauthenticated
from backend.app.auth.models import MembershipRow, Tenant, User, normalize_email
from backend.app.auth.passwords import MAX_LENGTH, MIN_LENGTH, dummy_verify, hash_password, verify_password
from backend.app.auth.permissions import Membership, Permission, Principal, Role, check_memberships
from backend.app.auth.tokens import configured, issue_token

router = APIRouter(prefix="/api/auth", tags=["auth"])
admin_router = APIRouter(prefix="/api/admin", tags=["admin"])
manage_users = require_tenant_permission(Permission.USER_MANAGE)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def valid_email(value: str) -> str:
    value = normalize_email(value)
    local, at, domain = value.partition("@")
    if not at or not local or not domain or "@" in domain or any(c.isspace() for c in value) or len(value) > 320:
        raise ValueError("invalid email")
    return value


class LoginIn(Strict):
    tenant_id: str = Field(min_length=1, max_length=128)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=MAX_LENGTH)


class MembershipIn(Strict):
    role: Role
    team_id: str | None = Field(default=None, min_length=1, max_length=128)


def checked(items: list[MembershipIn]) -> list[MembershipIn]:
    check_memberships([Membership(m.role, m.team_id) for m in items])
    return items


class UserCreate(Strict):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=MIN_LENGTH, max_length=MAX_LENGTH)
    memberships: list[MembershipIn] = Field(default_factory=list, max_length=100)

    @field_validator("email")
    @classmethod
    def email_format(cls, value):
        return valid_email(value)

    @field_validator("password")
    @classmethod
    def password_content(cls, value):
        if not value.strip():
            raise ValueError("password must not be blank")
        return value

    @field_validator("memberships")
    @classmethod
    def membership_rules(cls, value):
        return checked(value)


class MembershipsIn(Strict):
    memberships: list[MembershipIn] = Field(max_length=100)

    @field_validator("memberships")
    @classmethod
    def membership_rules(cls, value):
        return checked(value)


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime


def grants(memberships) -> list[dict]:
    items = [{"role": m.role.value if isinstance(m.role, Role) else m.role, "team_id": m.team_id} for m in memberships]
    return sorted(items, key=lambda m: (m["role"], m["team_id"] or ""))


def labels(memberships) -> list[str]:
    """Flat audit form, e.g. ["admin:*", "gestor:team-a"]; audit details allow scalars only."""
    return [f"{m['role']}:{m['team_id'] or '*'}" for m in grants(memberships)]


def audit(session, principal: Principal, action: str, user_id: str, details: dict | None = None):
    record_event(session, action=action, outcome="success", tenant_id=principal.tenant_id,
                 actor_user_id=principal.user_id, resource_type="user", resource_id=user_id,
                 details=details, trace_id=current_trace_id())


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, request: Request):
    settings = request.app.state.settings
    if not configured(settings):
        raise HTTPException(status_code=503, detail={"code": "AUTH_UNAVAILABLE", "message": "Authentication unavailable"})
    with request.app.state.session_factory() as session:
        tenant = session.get(Tenant, body.tenant_id)
        user = session.scalar(select(User).where(User.tenant_id == body.tenant_id,
                                                 User.email == normalize_email(body.email))) if tenant else None
        valid = verify_password(body.password, user.password_hash) if user else dummy_verify(body.password)
        if not (valid and user.active and tenant.active):
            if tenant:  # never record email or password; unknown tenants are not recorded at all
                record_event(session, action="auth.login", outcome="failure", tenant_id=tenant.tenant_id,
                             actor_user_id=user.user_id if user else None,
                             details={"reason": "invalid_credentials"}, trace_id=current_trace_id())
                session.commit()
            raise unauthenticated()
        token, expires_at = issue_token(settings, user_id=user.user_id, tenant_id=user.tenant_id,
                                        token_version=user.token_version)
        record_event(session, action="auth.login", outcome="success", tenant_id=user.tenant_id,
                     actor_user_id=user.user_id, trace_id=current_trace_id())
        session.commit()
    return LoginOut(access_token=token, expires_at=expires_at)


@router.get("/me")
def me(principal: Principal = Depends(get_principal)):
    return {"user_id": principal.user_id, "tenant_id": principal.tenant_id, "memberships": grants(principal.memberships)}


@router.post("/logout", status_code=204)
def logout(request: Request, principal: Principal = Depends(get_principal)):
    """Revokes every token of the user by bumping token_version."""
    with request.app.state.session_factory() as session:
        session.execute(update(User).where(User.user_id == principal.user_id, User.tenant_id == principal.tenant_id)
                        .values(token_version=User.token_version + 1))
        record_event(session, action="auth.logout", outcome="success", tenant_id=principal.tenant_id,
                     actor_user_id=principal.user_id, trace_id=current_trace_id())
        session.commit()
    return Response(status_code=204)


def tenant_user(session, principal: Principal, user_id: str) -> User:
    # Users of other tenants are indistinguishable from missing ones.
    user = session.scalar(select(User).where(User.user_id == user_id, User.tenant_id == principal.tenant_id))
    if user is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "User not found"})
    return user


def user_view(session, user: User) -> dict:
    rows = session.scalars(select(MembershipRow).where(MembershipRow.user_id == user.user_id,
                                                       MembershipRow.tenant_id == user.tenant_id))
    return {"user_id": user.user_id, "tenant_id": user.tenant_id, "email": user.email, "active": user.active,
            "memberships": grants(rows)}


def conflict(message: str) -> HTTPException:
    return HTTPException(status_code=409, detail={"code": "CONFLICT", "message": message})


@admin_router.post("/users", status_code=201)
def create_user(body: UserCreate, request: Request, principal: Principal = Depends(manage_users)):
    with request.app.state.session_factory() as session:
        user = User(tenant_id=principal.tenant_id, email=body.email, password_hash=hash_password(body.password))
        session.add(user)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            raise conflict("User already exists") from None
        session.add_all(MembershipRow(tenant_id=principal.tenant_id, user_id=user.user_id, role=m.role.value,
                                      team_id=m.team_id) for m in body.memberships)
        audit(session, principal, "admin.user.create", user.user_id, {"grants": labels(body.memberships)})
        session.commit()
        return user_view(session, user)


@admin_router.get("/users")
def list_users(request: Request, principal: Principal = Depends(manage_users)):
    with request.app.state.session_factory() as session:
        users = session.scalars(select(User).where(User.tenant_id == principal.tenant_id).order_by(User.email))
        return [user_view(session, user) for user in users]


@admin_router.put("/users/{user_id}/memberships")
def replace_memberships(user_id: str, body: MembershipsIn, request: Request,
                        principal: Principal = Depends(manage_users)):
    if user_id == principal.user_id:
        # Self-service may only drop grants: no self-escalation, and no lockout.
        if not {Membership(m.role, m.team_id) for m in body.memberships} <= set(principal.memberships):
            deny(request, principal, Permission.USER_MANAGE)
        if not any(m.role is Role.ADMIN and m.team_id is None for m in body.memberships):
            raise conflict("Cannot remove own tenant-wide admin membership")
    with request.app.state.session_factory() as session:
        user = tenant_user(session, principal, user_id)
        session.execute(delete(MembershipRow).where(MembershipRow.user_id == user.user_id))
        session.add_all(MembershipRow(tenant_id=principal.tenant_id, user_id=user.user_id, role=m.role.value,
                                      team_id=m.team_id) for m in body.memberships)
        audit(session, principal, "admin.user.memberships", user.user_id, {"grants": labels(body.memberships)})
        session.commit()
        return user_view(session, user)


@admin_router.post("/users/{user_id}/disable")
def disable_user(user_id: str, request: Request, principal: Principal = Depends(manage_users)):
    if user_id == principal.user_id:
        raise conflict("Cannot disable own account")
    with request.app.state.session_factory() as session:
        user = tenant_user(session, principal, user_id)
        session.execute(update(User).where(User.user_id == user.user_id)
                        .values(active=False, token_version=User.token_version + 1))
        audit(session, principal, "admin.user.disable", user.user_id)
        session.commit()
        session.refresh(user)
        return user_view(session, user)
