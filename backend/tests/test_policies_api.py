"""Policy API with real login: lifecycle, isolation, idempotency, and trace."""
import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.audit.models import AuditEvent
from backend.app.auth.cli import create_tenant, create_user
from backend.app.auth.permissions import Role
from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.policies.models import Policy

ROOT = Path(__file__).resolve().parents[2]
PASSWORD = "synthetic-test-password"
SOURCE = "SINTÉTICO — não é regra jurídica validada"
TRACE = "a10000000000000000000000000000aa"


def alembic(db):
    subprocess.run([sys.executable, "-m", "alembic", "-c", "backend/alembic.ini", "upgrade", "head"], cwd=ROOT,
                   env={**os.environ, "DATABASE_URL": f"sqlite:///{db.as_posix()}"}, check=True, capture_output=True)


def body(**overrides):
    payload = {
        "rule_key": "workweek.max_hours", "team_id": None, "employee_category": None, "title": "Jornada sintética",
        "parameters": {"max_hours": "8"}, "source_kind": "sintetico", "source_reference": SOURCE,
        "valid_from": "2026-01-01", "valid_until": None,
    }
    payload.update(overrides)
    return payload


def test_policy_api_flow(tmp_path):
    db = tmp_path / "api.db"
    alembic(db)
    app = create_app(Settings(f"sqlite:///{db.as_posix()}", auth_secret="s" * 40))
    sessions = app.state.session_factory
    create_tenant(sessions, "tenant-demo-a", "A")
    create_tenant(sessions, "tenant-demo-b", "B")
    create_user(sessions, "tenant-demo-a", "author@a.test", Role.RH, None, PASSWORD)
    create_user(sessions, "tenant-demo-a", "approver@a.test", Role.RH, None, PASSWORD)
    create_user(sessions, "tenant-demo-a", "gestor@a.test", Role.GESTOR, "team-aurora", PASSWORD)
    create_user(sessions, "tenant-demo-b", "rh@b.test", Role.RH, None, PASSWORD)

    with TestClient(app) as client:
        def login(tenant, email):
            response = client.post("/api/auth/login", json={"tenant_id": tenant, "email": email, "password": PASSWORD})
            assert response.status_code == 200, response.text
            return {"Authorization": f"Bearer {response.json()['access_token']}"}

        author, approver = login("tenant-demo-a", "author@a.test"), login("tenant-demo-a", "approver@a.test")
        gestor, other = login("tenant-demo-a", "gestor@a.test"), login("tenant-demo-b", "rh@b.test")

        assert client.get("/api/policies").status_code == 401
        assert client.post("/api/policies", json=body(), headers=gestor).status_code == 403
        assert client.post("/api/policies", json=body(tenant_id="tenant-demo-a"), headers=author).status_code == 422

        created = client.post("/api/policies", json=body(), headers={**author, "Idempotency-Key": "once"})
        assert created.status_code == 200, created.text
        policy_id = created.json()["policy_id"]
        version_id = created.json()["versions"][0]["version_id"]
        again = client.post("/api/policies", json=body(), headers={**author, "Idempotency-Key": "once"})
        assert again.json()["policy_id"] == policy_id
        clash = client.post("/api/policies", json=body(title="Outra"), headers={**author, "Idempotency-Key": "once"})
        assert clash.status_code == 409 and clash.json()["detail"]["code"] == "IDEMPOTENCY_CONFLICT"

        with Session(app.state.engine) as session:
            assert session.scalar(select(func.count()).select_from(Policy)) == 1
            assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "policy.create")) == 1

        assert client.get(f"/api/policies/{policy_id}", headers=other).status_code == 404
        assert client.get("/api/policies", headers=gestor).json()["items"][0]["policy_id"] == policy_id

        submit = client.post(f"/api/policies/{policy_id}/versions/{version_id}/submit",
                             json={"expected_revision": 0}, headers=author)
        assert submit.status_code == 200, submit.text
        stale = client.post(f"/api/policies/{policy_id}/versions/{version_id}/submit",
                            json={"expected_revision": 0}, headers=author)
        assert stale.status_code == 409 and stale.json()["detail"]["code"] == "STALE_REVISION"
        assert client.post(f"/api/policies/{policy_id}/versions/{version_id}/approve",
                           json={"expected_revision": 1, "legal_review_reference": "parecer"}, headers=author).status_code == 403
        approved = client.post(
            f"/api/policies/{policy_id}/versions/{version_id}/approve",
            json={"expected_revision": 1, "legal_review_reference": "parecer-sintetico"}, headers=approver)
        assert approved.status_code == 200 and approved.json()["status"] == "approved"

        resolved = client.get("/api/policies/resolve", params={
            "on_date": "2026-03-01", "team_id": "team-aurora", "rule_keys": "workweek.max_hours",
        }, headers={**author, "X-Trace-Id": TRACE})
        assert resolved.status_code == 200, resolved.text
        assert resolved.headers["x-trace-id"] == TRACE
        assert resolved.json()["complete"] is True
        assert resolved.json()["items"][0]["parameters"]["max_hours"] == "8"

        revoked = client.post(
            f"/api/policies/{policy_id}/versions/{version_id}/revoke",
            json={"expected_revision": 2, "revocation_reason": "substituida no teste"}, headers=approver)
        assert revoked.status_code == 200
        after = client.get("/api/policies/resolve", params={
            "on_date": "2026-03-01", "team_id": "team-aurora", "rule_keys": "workweek.max_hours",
        }, headers=author)
        assert after.json()["complete"] is False
        assert after.json()["items"][0]["status"] == "review_required"
        assert after.json()["items"][0]["parameters"] is None

        events = client.get("/api/audit", params={"trace_id": TRACE}, headers=author).json()["items"]
        assert [event["action"] for event in events] == ["policy.resolve"]
        assert "parecer" not in str(events) and "Jornada" not in str(events)
    app.state.engine.dispose()
