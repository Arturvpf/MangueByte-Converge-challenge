import math
import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import APIRouter, Depends, Request
from fastapi.testclient import TestClient
from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from backend.app.audit import models  # noqa: F401  registers audit_events
from backend.app.audit.api import router
from backend.app.audit.log import InvalidCursor, query_events, record_event
from backend.app.audit.models import AuditEvent, AuditImmutableError
from backend.app.audit.sanitize import sanitize_details
from backend.app.audit.tracing import current_trace_id, use_trace_id
from backend.app.auth.dependencies import get_principal
from backend.app.auth.permissions import Membership, Principal, Role
from backend.app.core.config import Settings
from backend.app.core.database import Base
from backend.app.core.modules import DomainModule
from backend.app.main import create_app

HEX = re.compile(r"^[0-9a-f]{32}$")
probe = APIRouter()


def dep_trace():
    return current_trace_id()


@probe.get("/probe")
def sync_probe(request: Request, dep: str = Depends(dep_trace)):
    return {"ctx": current_trace_id(), "state": request.state.trace_id, "dep": dep}


@probe.get("/probe-async")
async def async_probe():
    return {"ctx": current_trace_id()}


@probe.post("/probe-write")
def write_probe(request: Request):
    with request.app.state.session_factory() as s:
        record_event(s, action="probe.write", outcome="success", tenant_id="t-a", details={"n": 1})
        s.commit()
    return {}


@probe.get("/boom")
def boom():
    raise RuntimeError("boom")


def principal(*memberships, tenant="t-a", user="u-1"):
    return Principal(user, tenant, tuple(Membership(r, t) for r, t in memberships))


TENANT_WIDE = principal((Role.RH, None))
TEAM_1 = principal((Role.RH, "team-1"))
NO_AUDIT = principal((Role.GESTOR, None))


@pytest.fixture
def app(tmp_path):
    app = create_app(Settings(f"sqlite:///{(tmp_path / 'x.db').as_posix()}"),
                     modules=(DomainModule(routers=(router, probe)),))
    Base.metadata.create_all(app.state.engine)
    yield app
    app.state.engine.dispose()


def client(app, who=None):
    if who is not None:
        app.dependency_overrides[get_principal] = lambda: who
    return TestClient(app, raise_server_exceptions=False)


def seed(app, **kw):
    with Session(app.state.engine) as s:
        e = record_event(s, **{"action": "x.do", "outcome": "success", "tenant_id": "t-a", **kw})
        s.commit()
        return e.id


def events(app, **filters):
    with Session(app.state.engine) as s:
        return list(s.query(AuditEvent).filter_by(**filters))


def test_valid_trace_header_echoed_and_recorded(app):
    c = client(app)
    r = c.get("/probe", headers={"X-Trace-Id": "Req-1._~"})
    assert r.headers["x-trace-id"] == "Req-1._~"
    assert r.json() == {"ctx": "Req-1._~", "state": "Req-1._~", "dep": "Req-1._~"}
    assert c.get("/probe-async", headers={"X-Trace-Id": "async-1"}).json() == {"ctx": "async-1"}
    r = c.post("/probe-write", headers={"X-Trace-Id": "write-1"})
    assert r.headers["x-trace-id"] == "write-1"
    assert [e.trace_id for e in events(app, action="probe.write")] == ["write-1"]


@pytest.mark.parametrize("bad", ["has space", "a" * 129, "", "x;drop", "é"])
def test_invalid_trace_header_replaced(app, bad):
    r = client(app).get("/probe", headers={"X-Trace-Id": bad.encode("utf-8")})
    tid = r.headers["x-trace-id"]
    assert HEX.match(tid) and r.json()["ctx"] == tid


def test_trace_generated_when_absent_and_on_errors(app):
    c = client(app)
    a, b = c.get("/probe"), c.get("/probe")
    assert HEX.match(a.headers["x-trace-id"]) and a.headers["x-trace-id"] != b.headers["x-trace-id"]
    assert a.json()["ctx"] == a.headers["x-trace-id"]
    assert c.get("/missing", headers={"X-Trace-Id": "nf-1"}).headers["x-trace-id"] == "nf-1"
    r = c.get("/boom", headers={"X-Trace-Id": "err-1"})
    assert r.status_code == 500 and r.headers["x-trace-id"] == "err-1"


def test_trace_outside_request():
    assert current_trace_id() != current_trace_id()
    with use_trace_id("job-7") as tid:
        assert tid == current_trace_id() == "job-7"
    with use_trace_id("bad id") as tid:
        assert HEX.match(tid)
    assert current_trace_id() != "job-7"


def test_sanitizer_drops_and_redacts():
    out = sanitize_details({
        "team_count": 3, "ratio": 0.5, "ok": True, "missing": None, "ids": ["a", 1, None],
        "employee_name": "Ana", "user.email": "x", "prompt_text": "raw prompt", "salario_base": 10, "rg": "1",
        "cid_code": "F32", "target_id": "keep", "incident_id": "keep",
        "note": "contact ana@example.com", "doc": "123.456.789-09", "plain_digits": "12345678909",
        "nested": {"a": 1}, "deep_list": [[1]], "nan": math.nan, "inf": math.inf, "obj": object(),
        "long": "x" * 1000, "many": list(range(50)), "Bad Key": 1, 5: "int key", "_redacted": ["spoof"],
    })
    assert out["team_count"] == 3 and out["ratio"] == 0.5 and out["ok"] is True and out["missing"] is None
    assert out["ids"] == ["a", 1, None] and out["target_id"] == out["incident_id"] == "keep"
    assert out["note"] == out["doc"] == out["plain_digits"] == "[redacted]"
    assert out["long"] == "x" * 256 and out["many"] == list(range(20))
    for k in ("employee_name", "user.email", "prompt_text", "salario_base", "rg", "cid_code",
              "nested", "deep_list", "nan", "inf", "obj"):
        assert k not in out and k in out["_redacted"]
    assert "[invalid_key]" in out["_redacted"] and "Bad Key" not in str(out) and "spoof" not in str(out)
    assert "Ana" not in str(out) and "raw prompt" not in str(out)


def test_sanitizer_caps_and_types():
    out = sanitize_details({f"k{i}": i for i in range(40)})
    assert len([k for k in out if k != "_redacted"]) == 32 and "k39" in out["_redacted"]
    assert sanitize_details(None) == {}
    with pytest.raises(TypeError):
        sanitize_details(["a"])


def test_record_event_validation(app):
    with Session(app.state.engine) as s:
        base = {"action": "x.do", "outcome": "success", "tenant_id": "t-a"}
        for bad in ({"action": "Bad Action"}, {"action": "x" * 65}, {"outcome": "ok"}, {"actor_type": "robot"},
                    {"tenant_id": ""}, {"tenant_id": None}, {"trace_id": "bad id"}, {"team_id": "t" * 129},
                    {"actor_user_id": "u" * 37}):
            with pytest.raises(ValueError):
                record_event(s, **{**base, **bad})
        with pytest.raises(TypeError):
            record_event(s, **base, details="free text")
        with use_trace_id("ctx-1"):
            e = record_event(s, **base, actor_type="agent", details={"email": "a@b.co", "n": 2})
        assert e.trace_id == "ctx-1" and e.details == {"n": 2, "_redacted": ["email"]}
        assert e.occurred_at.tzinfo is not None
        s.commit()


def test_audit_is_append_only(app):
    ident = seed(app)
    with Session(app.state.engine) as s:
        e = s.get(AuditEvent, ident)
        e.outcome = "failure"
        with pytest.raises(AuditImmutableError):
            s.flush()
        s.rollback()
        s.delete(s.get(AuditEvent, ident))
        with pytest.raises(AuditImmutableError):
            s.flush()
        s.rollback()
        with pytest.raises(AuditImmutableError):
            s.execute(update(AuditEvent).values(outcome="failure"))
        with pytest.raises(AuditImmutableError):
            s.execute(delete(AuditEvent.__table__))
    assert events(app)[0].outcome == "success"


def test_query_isolation_by_tenant_and_team(app):
    seed(app, tenant_id="t-a")
    seed(app, tenant_id="t-a", team_id="team-1")
    seed(app, tenant_id="t-a", team_id="team-2")
    seed(app, tenant_id="t-b", team_id="team-1")
    with Session(app.state.engine) as s:
        wide, _ = query_events(s, tenant_id="t-a", team_ids=None)
        assert len(wide) == 3 and {e.tenant_id for e in wide} == {"t-a"}
        team, _ = query_events(s, tenant_id="t-a", team_ids=frozenset({"team-1"}))
        assert [(e.tenant_id, e.team_id) for e in team] == [("t-a", "team-1")]
        assert query_events(s, tenant_id="t-a", team_ids=frozenset()) == ([], None)
        other, _ = query_events(s, tenant_id="t-b", team_ids=None)
        assert [e.tenant_id for e in other] == ["t-b"]


def test_query_pagination_filters_and_cursor(app):
    with Session(app.state.engine) as s:
        for i in range(7):
            record_event(s, action="x.do", outcome="success", tenant_id="t-a", resource_id=f"r{i}", trace_id="tr-1")
        record_event(s, action="y.do", outcome="success", tenant_id="t-a", trace_id="tr-2")
        s.commit()
        everything, _ = query_events(s, tenant_id="t-a", team_ids=None, action="x.do", limit=500)
        seen, cursor = [], None
        while True:
            page, cursor = query_events(s, tenant_id="t-a", team_ids=None, trace_id="tr-1", limit=3, cursor=cursor)
            seen += page
            if cursor is None:
                break
        assert [e.id for e in seen] == [e.id for e in everything] and len(seen) == 7
        assert [e.occurred_at for e in seen] == sorted((e.occurred_at for e in seen), reverse=True)
        first, cursor = query_events(s, tenant_id="t-a", team_ids=None, action="x.do", limit=3)
        record_event(s, action="x.do", outcome="success", tenant_id="t-a")  # newer event must not shift pages
        s.commit()
        second, _ = query_events(s, tenant_id="t-a", team_ids=None, action="x.do", limit=3, cursor=cursor)
        assert [e.id for e in second] == [e.id for e in everything[3:6]]
        assert len(query_events(s, tenant_id="t-a", team_ids=None, limit=0)[0]) == 1
        future = datetime.now(timezone.utc) + timedelta(days=1)
        assert query_events(s, tenant_id="t-a", team_ids=None, since=future) == ([], None)
        assert len(query_events(s, tenant_id="t-a", team_ids=None, until=future, limit=500)[0]) == 9
        with pytest.raises(InvalidCursor):
            query_events(s, tenant_id="t-a", team_ids=None, cursor="not-a-cursor")


def test_api_requires_audit_read_and_records_denial(app):
    r = client(app, NO_AUDIT).get("/api/audit", headers={"X-Trace-Id": "deny-1"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "FORBIDDEN_SCOPE"
    [e] = events(app, action="audit.read")
    assert (e.outcome, e.trace_id, e.actor_user_id) == ("denied", "deny-1", "u-1")


def test_api_scope_and_recorded_read(app):
    seed(app, tenant_id="t-a")
    seed(app, tenant_id="t-a", team_id="team-1", details={"n": 1})
    seed(app, tenant_id="t-a", team_id="team-2")
    seed(app, tenant_id="t-b", team_id="team-1")
    c = client(app, TEAM_1)
    r = c.get("/api/audit", params={"tenant_id": "t-b"})
    assert r.status_code == 200 and [i["team_id"] for i in r.json()["items"]] == ["team-1"]
    item = r.json()["items"][0]
    assert item["details"] == {"n": 1} and item["occurred_at"].endswith("+00:00") and "tenant_id" not in item
    assert c.get("/api/audit", params={"team_id": "team-2"}).status_code == 403
    assert c.get("/api/audit", params={"team_id": "team-1"}).status_code == 200

    c = client(app, TENANT_WIDE)
    r = c.get("/api/audit", params={"action": "x.do", "limit": 500}, headers={"X-Trace-Id": "read-1"})
    assert r.status_code == 200 and len(r.json()["items"]) == 3 and r.json()["next_cursor"] is None
    assert [i["team_id"] for i in c.get("/api/audit", params={"team_id": "team-2", "action": "x.do"}).json()["items"]] == ["team-2"]
    [read] = events(app, action="audit.read", trace_id="read-1")
    assert read.outcome == "success" and read.tenant_id == "t-a"
    assert read.details == {"filters": ["action"], "result_count": 3}
    r = c.get("/api/audit", params={"trace_id": "read-1"})
    assert [i["action"] for i in r.json()["items"]] == ["audit.read"]
    assert c.get("/api/audit", params={"cursor": "junk"}).json()["detail"]["code"] == "INVALID_CURSOR"
    assert c.get("/api/audit", params={"limit": 501}).status_code == 422

    page = c.get("/api/audit", params={"limit": 2}).json()
    rest = c.get("/api/audit", params={"limit": 2, "cursor": page["next_cursor"]}).json()
    assert page["next_cursor"] and not {i["id"] for i in page["items"]} & {i["id"] for i in rest["items"]}
