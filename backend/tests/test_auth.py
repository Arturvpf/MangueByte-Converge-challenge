import base64
from datetime import datetime, timedelta, timezone
from functools import cache
import hashlib
import hmac
import json
import time

from fastapi import APIRouter, Depends, Request
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.audit.models import AuditEvent
from backend.app.auth.api import admin_router, router
from backend.app.auth.dependencies import require_permission, require_team_permission
from backend.app.auth.models import MembershipRow, Tenant, User
from backend.app.auth.passwords import dummy_verify, hash_password, verify_password
from backend.app.auth.permissions import Membership, Permission, Principal, Role
from backend.app.auth.tokens import InvalidToken, issue_token, verify_token
from backend.app.auth.tools import PrincipalBoundary, ToolForbidden, authorize_tool
from backend.app.core.config import Settings
from backend.app.core.database import Base
from backend.app.core.modules import DomainModule
from backend.app.jobs.engine import MockExecutor, Scope
from backend.app.jobs.models import JobsBase
from backend.app.main import create_app

SECRET = "s" * 40
PASSWORD = "correct horse battery"
P = Permission

probe = APIRouter()


@probe.get("/probe/teams/{team_id}")
def team_probe(team_id: str, principal: Principal = Depends(require_team_permission(P.DATA_READ))):
    return {"tenant_id": principal.tenant_id, "team_id": team_id}


@probe.get("/probe/misconfigured")
def misconfigured_probe(principal: Principal = Depends(require_team_permission(P.DATA_READ))):
    return {"ok": True}


@probe.post("/probe/boundary/{team}")
def boundary_probe(team: str, request: Request, principal: Principal = Depends(require_permission(P.INVESTIGATION_RUN))):
    PrincipalBoundary.for_request(request, principal).authorize("create", Scope(principal.tenant_id, team, "s", "t"))
    return {"ok": True}


@probe.get("/probe/read")
def read_probe(principal: Principal = Depends(require_permission(P.DATA_READ))):
    return {"user_id": principal.user_id}


@cache
def stored_hash():
    return hash_password(PASSWORD)


USERS = {  # key: (tenant, email, memberships)
    "admin_a": ("a", "Admin@A.example", [("admin", None)]),
    "gestor_a": ("a", "gestor@a.example", [("gestor", "t1")]),
    "rh_a": ("a", "rh@a.example", [("rh", None)]),
    "admin_b": ("b", "admin@b.example", [("admin", None)]),
    "gestor_b": ("b", "gestor@b.example", [("gestor", "t1")]),
}


def build(tmp_path, secret=SECRET):
    app = create_app(Settings(f"sqlite:///{(tmp_path / 'auth.db').as_posix()}", auth_secret=secret),
                     modules=(DomainModule(routers=(router, admin_router, probe)),))
    Base.metadata.create_all(app.state.engine)
    ids = {}
    with app.state.session_factory() as s:
        s.add_all([Tenant(tenant_id="a", name="A"), Tenant(tenant_id="b", name="B")])
        s.flush()
        for key, (tenant, email, grants) in USERS.items():
            user = User(tenant_id=tenant, email=email, password_hash=stored_hash())
            s.add(user)
            s.flush()
            ids[key] = user.user_id
            s.add_all(MembershipRow(tenant_id=tenant, user_id=user.user_id, role=r, team_id=t) for r, t in grants)
        s.commit()
    return app, ids


@pytest.fixture
def env(tmp_path):
    app, ids = build(tmp_path)
    with TestClient(app) as client:
        yield app, client, ids


def login(client, key, password=PASSWORD):
    tenant, email, _ = USERS[key]
    return client.post("/api/auth/login", json={"tenant_id": tenant, "email": email, "password": password})


def auth(client, key):
    response = login(client, key)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def events(app, action=None):
    with app.state.session_factory() as s:
        query = select(AuditEvent).order_by(AuditEvent.occurred_at)
        return list(s.scalars(query.where(AuditEvent.action == action) if action else query))


def b64(value) -> str:
    raw = value if isinstance(value, bytes) else json.dumps(value).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def test_password_hash_and_verify():
    encoded = hash_password(PASSWORD)
    assert encoded.startswith("scrypt$16384$8$1$") and PASSWORD not in encoded
    assert verify_password(PASSWORD, encoded) and not verify_password(PASSWORD + "!", encoded)
    assert hash_password(PASSWORD) != encoded  # salted
    for bad in ("", "scrypt$x", "bcrypt$16384$8$1$AAAA$AAAA", encoded.replace("$8$", "$0$"), None):
        assert not verify_password(PASSWORD, bad)
    assert not verify_password("", encoded) and not verify_password(None, encoded)
    for weak in ("", "short", " " * 20, "x" * 2000):
        with pytest.raises(ValueError):
            hash_password(weak)
    assert dummy_verify(PASSWORD) is False and dummy_verify("") is False


def test_token_roundtrip_and_rejections():
    settings = Settings(auth_secret=SECRET)
    token, expires_at = issue_token(settings, user_id="u1", tenant_id="a", token_version=3)
    claims = verify_token(settings, token)
    assert (claims["iss"], claims["sub"], claims["tid"], claims["ver"]) == ("alinia", "u1", "a", 3)
    assert expires_at > datetime.now(timezone.utc) and claims["jti"]
    header, payload, signature = token.split(".")
    forged = dict(claims, tid="b")
    sign = lambda key, h, p: b64(hmac.new(key.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest())
    bad = [
        f"{header}.{b64(forged)}.{signature}",  # tampered payload
        f"{b64({'alg': 'none', 'typ': 'JWT'})}.{payload}.",  # alg none
        f"{b64({'alg': 'none', 'typ': 'JWT'})}.{payload}.{signature}",
        f"{b64({'alg': 'HS512', 'typ': 'JWT'})}.{payload}.{sign(SECRET, b64({'alg': 'HS512', 'typ': 'JWT'}), payload)}",
        f"{header}.{payload}.{sign('w' * 40, header, payload)}",  # wrong secret
        f"{header}.{payload}.{signature[:-2]}",
        f"{header}.{payload}.{signature}=",
        f"{header}.{payload}.{signature}.x", "", "a.b", "...", "é.é.é", "x" * 5000, None, 42,
    ]
    for value in bad:
        with pytest.raises(InvalidToken):
            verify_token(settings, value)
    with pytest.raises(InvalidToken):  # expired
        verify_token(settings, token, now=time.time() + 3601)
    with pytest.raises(InvalidToken):
        verify_token(Settings(auth_secret="w" * 40), token)
    for secret in (None, "short"):
        with pytest.raises(InvalidToken):
            verify_token(Settings(auth_secret=secret), token)
        with pytest.raises(RuntimeError):
            issue_token(Settings(auth_secret=secret), user_id="u1", tenant_id="a", token_version=0)
    # A correctly signed token with a non-integer version or wrong issuer is still rejected.
    for claims_bad in (dict(claims, ver="3"), dict(claims, iss="other"), dict(claims, sub="")):
        p = b64(claims_bad)
        with pytest.raises(InvalidToken):
            verify_token(settings, f"{header}.{p}.{sign(SECRET, header, p)}")


def test_hostile_token_shapes_give_401_not_500(env):
    app, client, ids = env
    token = auth(client, "gestor_a")["Authorization"].split()[1]
    header, payload, signature = token.split(".")
    deep = f"{b64(b'[' * 3000)}.e30.AAAA"  # ~4009 chars: would recurse in json.loads
    assert len(deep) <= 4096
    for value in (deep, f"{header}.{payload}\u00e9.{signature}", f"{header}.{payload[:-1]}\u00e9.{signature}",
                  f"{header}.{payload}.{signature}\u00e9", f"{header}.{payload}+/.{signature}", f"{header}..{signature}"):
        response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {value}".encode()})
        assert response.status_code == 401, value[:40]
    # Even a correctly signed deep-nesting header is rejected cleanly.
    h = b64(b"[" * 3000)
    signed = f"{h}.e30.{b64(hmac.new(SECRET.encode(), f'{h}.e30'.encode(), hashlib.sha256).digest())}"
    with pytest.raises(InvalidToken):
        verify_token(app.state.settings, signed)


def test_login_me_and_generic_failures(env):
    app, client, ids = env
    ok = login(client, "admin_a")
    assert ok.status_code == 200 and ok.json()["token_type"] == "bearer" and ok.json()["expires_at"]
    headers = {"Authorization": f"Bearer {ok.json()['access_token']}"}
    me = client.get("/api/auth/me", headers=headers)
    assert me.json() == {"user_id": ids["admin_a"], "tenant_id": "a", "memberships": [{"role": "admin", "team_id": None}]}
    assert "password" not in me.text
    assert client.post("/api/auth/login", json={"tenant_id": "a", "email": "  ADMIN@a.example ",
                                                 "password": PASSWORD}).status_code == 200
    failures = [
        login(client, "admin_a", "wrong password!"),
        client.post("/api/auth/login", json={"tenant_id": "zzz", "email": "admin@a.example", "password": PASSWORD}),
        client.post("/api/auth/login", json={"tenant_id": "a", "email": "nobody@a.example", "password": PASSWORD}),
        client.post("/api/auth/login", json={"tenant_id": "b", "email": "admin@a.example", "password": PASSWORD}),
    ]
    assert {r.status_code for r in failures} == {401}
    assert len({r.text for r in failures}) == 1 and failures[0].headers["www-authenticate"] == "Bearer"
    logins = events(app, "auth.login")
    assert {(e.tenant_id, e.outcome) for e in logins} == {("a", "success"), ("a", "failure"), ("b", "failure")}
    assert all("zzz" != e.tenant_id for e in events(app))
    for e in events(app):
        assert "@" not in json.dumps(e.details) and PASSWORD not in json.dumps(e.details)


def test_missing_or_short_secret_fails_closed(tmp_path):
    token, _ = issue_token(Settings(auth_secret=SECRET), user_id="u", tenant_id="a", token_version=0)
    for index, secret in enumerate((None, "short")):
        folder = tmp_path / str(index)
        folder.mkdir()
        app, _ = build(folder, secret)
        with TestClient(app) as client:
            response = login(client, "admin_a")
            assert response.status_code == 503 and "access_token" not in response.text
            assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
            assert client.get("/api/admin/users", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_bearer_parsing_and_forged_claims(env):
    app, client, ids = env
    token = auth(client, "gestor_a")["Authorization"].split()[1]
    for value in (None, "Basic abc", "Bearer", "Bearer ", f"Bearer  {token}", f"Token {token}",
                  f"Bearer {token[:-3]}abc", f"Bearer {token} x"):
        response = client.get("/api/auth/me", headers={"Authorization": value} if value else {})
        assert response.status_code == 401 and response.json()["detail"]["code"] == "UNAUTHENTICATED"
        assert response.headers["www-authenticate"] == "Bearer"
    assert client.get("/api/auth/me", headers={"authorization": f"bearer {token}"}).status_code == 200
    settings = app.state.settings
    for claims in ({"user_id": ids["gestor_a"], "tenant_id": "b", "token_version": 0},  # claim of another tenant
                   {"user_id": "missing", "tenant_id": "a", "token_version": 0},
                   {"user_id": ids["gestor_a"], "tenant_id": "a", "token_version": 7}):
        forged, _ = issue_token(settings, **claims)
        assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_logout_revokes_all_tokens(env):
    app, client, ids = env
    first, second = auth(client, "gestor_a"), auth(client, "gestor_a")
    assert client.post("/api/auth/logout", headers=first).status_code == 204
    assert client.get("/api/auth/me", headers=first).status_code == 401
    assert client.get("/api/auth/me", headers=second).status_code == 401
    assert client.get("/api/auth/me", headers=auth(client, "gestor_a")).status_code == 200
    assert [e.actor_user_id for e in events(app, "auth.logout")] == [ids["gestor_a"]]


def test_disabled_user_and_inactive_tenant_rejected(env):
    app, client, ids = env
    admin, gestor = auth(client, "admin_a"), auth(client, "gestor_a")
    response = client.post(f"/api/admin/users/{ids['gestor_a']}/disable", headers=admin)
    assert response.status_code == 200 and response.json()["active"] is False
    assert client.get("/api/auth/me", headers=gestor).status_code == 401
    assert login(client, "gestor_a").status_code == 401
    event, = events(app, "admin.user.disable")
    assert (event.resource_type, event.resource_id, event.actor_user_id) == ("user", ids["gestor_a"], ids["admin_a"])
    rh = auth(client, "rh_a")
    with app.state.session_factory() as s:
        s.get(Tenant, "a").active = False
        s.commit()
    assert client.get("/api/auth/me", headers=rh).status_code == 401
    assert login(client, "rh_a").status_code == 401


def test_identity_in_body_is_rejected_and_tenants_isolated(env):
    app, client, ids = env
    admin = auth(client, "admin_a")
    body = {"email": "new@a.example", "password": "another long pass", "memberships": [{"role": "gestor", "team_id": "t2"}]}
    for extra in ({"tenant_id": "b"}, {"user_id": ids["admin_b"]}, {"actor_user_id": ids["admin_b"]}):
        assert client.post("/api/admin/users", headers=admin, json={**body, **extra}).status_code == 422
    assert client.post("/api/admin/users", headers=admin,
                       json={**body, "memberships": [{"role": "admin", "team_id": None, "tenant_id": "b"}]}).status_code == 422
    created = client.post("/api/admin/users", headers=admin, json=body)
    assert created.status_code == 201
    assert created.json()["tenant_id"] == "a" and "password" not in created.text
    assert created.json()["memberships"] == [{"role": "gestor", "team_id": "t2"}]
    listed = client.get("/api/admin/users", headers=admin).json()
    assert {u["user_id"] for u in listed} == {ids["admin_a"], ids["gestor_a"], ids["rh_a"], created.json()["user_id"]}
    assert all("password_hash" not in u for u in listed)
    foreign = ids["gestor_b"]
    assert client.put(f"/api/admin/users/{foreign}/memberships", headers=admin,
                      json={"memberships": [{"role": "admin", "team_id": None}]}).status_code == 404
    assert client.post(f"/api/admin/users/{foreign}/disable", headers=admin).status_code == 404
    assert client.post("/api/admin/users/nonexistent/disable", headers=admin).json() == \
        client.post(f"/api/admin/users/{foreign}/disable", headers=admin).json()
    with app.state.session_factory() as s:
        assert s.get(User, foreign).active and s.get(User, foreign).token_version == 0
    event, = events(app, "admin.user.create")
    assert event.details == {"grants": ["gestor:t2"]} and event.tenant_id == "a"
    assert client.post("/api/auth/login", json={"tenant_id": "a", "email": "new@a.example",
                                                 "password": "another long pass"}).status_code == 200


def test_memberships_of_other_tenant_grant_nothing(env):
    app, client, ids = env
    with app.state.session_factory() as s:  # corrupt row: user of A with a membership stamped with tenant B
        s.add(MembershipRow(tenant_id="b", user_id=ids["gestor_a"], role="admin", team_id=None))
        s.add(MembershipRow(tenant_id="a", user_id=ids["gestor_a"], role="superuser", team_id=None))
        # Invalid stored grants (rows written outside the API): a tenant-wide gestor and a blank team.
        s.add(MembershipRow(tenant_id="a", user_id=ids["gestor_a"], role="gestor", team_id=None))
        s.add(MembershipRow(tenant_id="a", user_id=ids["gestor_a"], role="rh", team_id="  "))
        s.commit()
    gestor = auth(client, "gestor_a")
    assert client.get("/api/auth/me", headers=gestor).json()["memberships"] == [{"role": "gestor", "team_id": "t1"}]
    assert client.get("/api/admin/users", headers=gestor).status_code == 403
    assert client.get("/probe/teams/t9", headers=gestor).status_code == 403
    assert client.get("/probe/teams/t1", headers=gestor).status_code == 200


def test_non_admins_cannot_call_admin_routes(env):
    app, client, ids = env
    for key in ("gestor_a", "rh_a"):
        headers = auth(client, key)
        responses = [client.get("/api/admin/users", headers=headers),
                     client.post("/api/admin/users", headers=headers, json={"email": "x@a.example", "password": PASSWORD}),
                     client.post(f"/api/admin/users/{ids['admin_a']}/disable", headers=headers),
                     client.put(f"/api/admin/users/{ids[key]}/memberships", headers=headers,
                                json={"memberships": [{"role": "admin", "team_id": None}]})]
        for response in responses:
            assert response.status_code == 403 and response.json()["detail"]["code"] == "FORBIDDEN_SCOPE"
    denied = events(app, "authz.denied")
    assert len(denied) == 8 and {e.details["permission"] for e in denied} == {"user:manage"}
    assert {e.outcome for e in denied} == {"denied"} and {e.tenant_id for e in denied} == {"a"}
    with app.state.session_factory() as s:
        assert s.get(User, ids["admin_a"]).active
        assert [r.role for r in s.scalars(select(MembershipRow).where(MembershipRow.user_id == ids["gestor_a"]))] == ["gestor"]
    assert client.get("/api/admin/users").status_code == 401


def test_membership_validation(env):
    app, client, ids = env
    admin = auth(client, "admin_a")
    invalid = [
        [{"role": "gestor", "team_id": None}], [{"role": "gestor"}],
        [{"role": "rh", "team_id": "t1"}, {"role": "rh", "team_id": "t1"}],
        [{"role": "admin", "team_id": None}, {"role": "admin"}],
        [{"role": "superuser", "team_id": None}], [{"role": "gestor", "team_id": ""}],
        [{"role": "gestor", "team_id": " t1"}],
    ]
    for memberships in invalid:
        assert client.post("/api/admin/users", headers=admin, json={"email": "x@a.example", "password": PASSWORD,
                                                                    "memberships": memberships}).status_code == 422
        assert client.put(f"/api/admin/users/{ids['gestor_a']}/memberships", headers=admin,
                          json={"memberships": memberships}).status_code == 422
    for body in ({"email": "x@a.example", "password": "short"}, {"email": "not-an-email", "password": PASSWORD},
                 {"email": "a b@a.example", "password": PASSWORD}, {"email": "x@a.example", "password": " " * 14}):
        assert client.post("/api/admin/users", headers=admin, json=body).status_code == 422
    assert client.post("/api/admin/users", headers=admin,
                       json={"email": "GESTOR@a.example", "password": PASSWORD}).status_code == 409
    gestor_b_mail = client.post("/api/admin/users", headers=admin, json={"email": "gestor@b.example", "password": PASSWORD})
    assert gestor_b_mail.status_code == 201  # same email in another tenant is a distinct account
    response = client.put(f"/api/admin/users/{ids['gestor_a']}/memberships", headers=admin,
                          json={"memberships": [{"role": "gestor", "team_id": "t1"}, {"role": "gestor", "team_id": "t2"},
                                                {"role": "rh", "team_id": "t3"}]})
    assert response.status_code == 200
    assert client.get("/api/auth/me", headers=auth(client, "gestor_a")).json()["memberships"] == [
        {"role": "gestor", "team_id": "t1"}, {"role": "gestor", "team_id": "t2"}, {"role": "rh", "team_id": "t3"}]
    event, = events(app, "admin.user.memberships")
    assert event.details == {"grants": ["gestor:t1", "gestor:t2", "rh:t3"]}
    assert events(app, "admin.user.create")[0].details == {"grants": []}
    assert not any("@" in json.dumps(e.details) for e in events(app))


def test_admin_cannot_lock_themselves_out(env):
    app, client, ids = env
    admin = auth(client, "admin_a")
    me = ids["admin_a"]
    assert client.post(f"/api/admin/users/{me}/disable", headers=admin).status_code == 409
    assert client.put(f"/api/admin/users/{me}/memberships", headers=admin, json={"memberships": []}).status_code == 409
    kept = client.put(f"/api/admin/users/{me}/memberships", headers=admin,
                      json={"memberships": [{"role": "admin", "team_id": None}]})
    assert kept.status_code == 200
    assert client.get("/api/auth/me", headers=admin).json()["memberships"] == [{"role": "admin", "team_id": None}]


def test_admin_cannot_escalate_own_grants(env):
    app, client, ids = env
    admin = auth(client, "admin_a")
    me = ids["admin_a"]
    for memberships in ([{"role": "admin", "team_id": None}, {"role": "rh", "team_id": None}],
                        [{"role": "admin", "team_id": None}, {"role": "gestor", "team_id": "t1"}],
                        [{"role": "rh", "team_id": None}], [{"role": "admin", "team_id": "t1"}]):
        response = client.put(f"/api/admin/users/{me}/memberships", headers=admin, json={"memberships": memberships})
        assert response.status_code == 403 and response.json()["detail"]["code"] == "FORBIDDEN_SCOPE"
    assert client.get("/api/auth/me", headers=admin).json()["memberships"] == [{"role": "admin", "team_id": None}]
    assert client.get("/probe/teams/t1", headers=admin).status_code == 403
    assert not events(app, "admin.user.memberships") and len(events(app, "authz.denied")) == 5


def test_team_and_permission_dependencies(env):
    app, client, ids = env
    gestor, admin, rh, gestor_b = (auth(client, k) for k in ("gestor_a", "admin_a", "rh_a", "gestor_b"))
    assert client.get("/probe/teams/t1", headers=gestor).json() == {"tenant_id": "a", "team_id": "t1"}
    assert client.get("/probe/teams/t2", headers=gestor).status_code == 403
    assert client.get("/probe/teams/t2", headers=rh).status_code == 200  # tenant-wide
    assert client.get("/probe/teams/t1", headers=admin).status_code == 403  # admin has no planning data
    # Team t1 of tenant B is a different team: the principal's tenant is what scopes it.
    assert client.get("/probe/teams/t1", headers=gestor_b).json()["tenant_id"] == "b"
    assert client.get("/probe/read", headers=gestor).status_code == 200
    assert client.get("/probe/read", headers=admin).status_code == 403
    assert client.get("/probe/teams/t1").status_code == 401
    denied = events(app, "authz.denied")
    assert [(e.team_id, e.details) for e in denied] == [
        (None, {"permission": "data:read", "target_team": "t2"}), (None, {"permission": "data:read", "target_team": "t1"}),
        (None, {"permission": "data:read"})]


def test_denied_team_path_never_stores_personal_data(env):
    app, client, ids = env
    gestor = auth(client, "gestor_a")
    for team in ("joao.silva@empresa.com", "joao%40empresa.com", "Joao Silva", "x" * 200):
        assert client.get(f"/probe/teams/{team}", headers=gestor).status_code == 403
    denied = events(app, "authz.denied")
    assert len(denied) == 4 and all(e.team_id is None and e.details == {"permission": "data:read"} for e in denied)
    dumped = json.dumps([[e.team_id, e.resource_id, e.details] for e in denied])
    assert "joao" not in dumped.lower() and "@" not in dumped


def test_team_permission_reads_path_only(env):
    app, client, ids = env
    gestor = auth(client, "gestor_a")
    response = client.get("/probe/misconfigured?team_id=t1", headers=gestor)
    assert response.status_code == 500 and response.json()["detail"]["code"] == "MISCONFIGURED_ROUTE"
    assert client.get("/probe/teams/t2?team_id=t1", headers=gestor).status_code == 403


def test_authorize_tool():
    gestor = Principal("u1", "a", (Membership(Role.GESTOR, "t1"),))
    rh = Principal("u2", "a", (Membership(Role.RH, None),))
    assert authorize_tool(gestor, P.INVESTIGATION_RUN, tenant_id="a", team_id="t1") is gestor
    assert authorize_tool(rh, P.DECISION_WRITE, tenant_id="a", team_id="t9") is rh
    assert authorize_tool(rh, P.DECISION_WRITE, tenant_id="a", team_id=None) is rh
    denied = [
        (gestor, P.INVESTIGATION_RUN, "a", "t2"), (gestor, P.INVESTIGATION_RUN, "b", "t1"),
        (gestor, P.INVESTIGATION_RUN, "a", None), (gestor, P.DECISION_WRITE, "a", "t1"),
        (rh, P.DECISION_WRITE, "b", "t1"), (rh, P.DECISION_WRITE, "a", ""), (rh, P.USER_MANAGE, "a", None),
        (rh, "decision:write", "a", "t1"), (None, P.DATA_READ, "a", "t1"),
    ]
    for principal, permission, tenant, team in denied:
        with pytest.raises(ToolForbidden):
            authorize_tool(principal, permission, tenant_id=tenant, team_id=team)
    assert issubclass(ToolForbidden, PermissionError)


def worker_db(tmp_path, users):
    engine = create_engine(f"sqlite:///{(tmp_path / 'jobs.db').as_posix()}")
    Base.metadata.create_all(engine)
    JobsBase.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    with sessions() as s:
        s.add(Tenant(tenant_id="a", name="A"))
        for user_id, role, team in users:
            s.add(User(user_id=user_id, tenant_id="a", email=f"{user_id}@a.example", password_hash="x"))
            s.flush()
            s.add(MembershipRow(tenant_id="a", user_id=user_id, role=role, team_id=team))
        s.commit()
    return engine, sessions


def test_principal_boundary_with_worker(tmp_path):
    engine, sessions = worker_db(tmp_path, (("u1", "gestor", "t1"), ("u2", "admin", None)))
    bound = lambda user_id: PrincipalBoundary(sessions, user_id=user_id, tenant_id="a", token_version=0)
    deadline = datetime.now(timezone.utc) + timedelta(hours=1)
    own = Scope("a", "t1", "snap", "trace-1")
    boundary = bound("u1")
    worker = MockExecutor(sessions, boundary)
    run_id = worker.create(own, "key", max_steps=5, max_cost=0, deadline=deadline)
    assert worker.claim(run_id, own)
    for scope in (Scope("b", "t1", "snap", "trace-2"), Scope("a", "t2", "snap", "trace-3")):
        with pytest.raises(PermissionError):
            worker.create(scope, "key2", max_steps=5, max_cost=0, deadline=deadline)
        with pytest.raises(PermissionError):
            worker.claim(run_id, scope)
    with pytest.raises(PermissionError):
        MockExecutor(sessions, bound("u2")).create(own, "key3", max_steps=5, max_cost=0, deadline=deadline)
    for operation in ("delete", "approve", "", "create "):
        with pytest.raises(ToolForbidden):
            boundary.authorize(operation, own)
    boundary.audit("create", own, run_id, 0)
    boundary.audit("claim", Scope("a", "t1", "snap", "not a valid trace"), run_id, 1)  # invalid trace replaced
    for scope in (Scope("b", "t1", "snap", "trace-1"), Scope("a", "t2", "snap", "trace-1")):
        with pytest.raises(ToolForbidden):
            boundary.audit("create", scope, run_id, 0)
    with pytest.raises(ToolForbidden):
        bound("u2").audit("create", own, run_id, 0)
    with sessions() as s:
        rows = list(s.scalars(select(AuditEvent)))
    job, = [e for e in rows if e.action == "job.create"]
    assert (job.tenant_id, job.team_id, job.trace_id, job.resource_id, job.actor_user_id) == ("a", "t1", "trace-1", run_id, "u1")
    claim, = [e for e in rows if e.action == "job.claim"]
    assert claim.trace_id != "not a valid trace"
    denied = [e for e in rows if e.action == "authz.denied"]
    assert len(denied) == 9 and {e.tenant_id for e in denied} == {"a"}  # never the envelope's tenant
    assert {e.trace_id for e in denied} >= {"trace-2", "trace-3"}
    engine.dispose()


@pytest.mark.parametrize("revoke", ["disable", "logout", "memberships", "tenant"])
def test_principal_boundary_revocation_mid_run(tmp_path, revoke):
    engine, sessions = worker_db(tmp_path, (("u1", "gestor", "t1"),))
    own = Scope("a", "t1", "snap", "trace-1")
    worker = MockExecutor(sessions, PrincipalBoundary(sessions, user_id="u1", tenant_id="a", token_version=0))
    run_id = worker.create(own, "key", max_steps=5, max_cost=0, deadline=datetime.now(timezone.utc) + timedelta(hours=1))
    token = worker.claim(run_id, own)
    assert token
    with sessions() as s:
        user = s.get(User, "u1")
        if revoke == "disable":
            user.active = False
        elif revoke == "logout":
            user.token_version += 1
        elif revoke == "tenant":
            s.get(Tenant, "a").active = False
        else:
            for row in s.scalars(select(MembershipRow)):
                s.delete(row)
        s.commit()
    with pytest.raises(PermissionError):
        worker.step(run_id, own, token)
    with pytest.raises(PermissionError):
        worker.heartbeat(run_id, own, token)
    engine.dispose()


def test_boundary_for_request_uses_token_version(env):
    app, client, ids = env
    gestor = auth(client, "gestor_a")
    assert client.post("/probe/boundary/t1", headers=gestor).json() == {"ok": True}
    with pytest.raises(ToolForbidden):
        client.post("/probe/boundary/t2", headers=gestor)
    client.post("/api/auth/logout", headers=auth(client, "gestor_a"))
    assert client.post("/probe/boundary/t1", headers=gestor).status_code == 401
