"""Restart, revoked rule, infeasible approval and investigation audit."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from fastapi.testclient import TestClient

from backend.app.auth.cli import create_tenant, create_user
from backend.app.auth.permissions import Membership, Principal, Role
from backend.app.core.config import Settings
from backend.app.flow.models import CriticRow, ScenarioRow, SimulationRow
from backend.app.main import create_app
from backend.app.policies.fixtures import load_synthetic
from backend.tests.test_workforce import HEADER, PASSWORD, line, migrate, weeks

ANSWER = "resposta-int02-nao-sai-na-trilha"
REASON = "motivo-int02-nao-sai-na-trilha"


def login(client, tenant, email):
    response = client.post("/api/auth/login", json={"tenant_id": tenant, "email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def finish(client, run_id, headers):
    state = client.post(f"/api/investigations/{run_id}/advance", headers=headers)
    assert state.status_code == 200, state.text
    body = state.json()
    for _ in range(6):
        if body["state"] != "WAITING_INPUT":
            return body
        for question in body["report"]["questions"]:
            if question["status"] != "pending":
                continue
            answered = client.post(f"/api/investigations/{run_id}/answers", json={
                "question_id": question["question_id"], "answer": ANSWER, "idempotency_key": "int02-" + question["question_id"],
            }, headers=headers)
            assert answered.status_code == 200, answered.text
        state = client.post(f"/api/investigations/{run_id}/advance", headers=headers)
        assert state.status_code == 200, state.text
        body = state.json()
    raise AssertionError(body["state"])


def test_restart_keeps_two_teams_and_short_history(tmp_path):
    db = tmp_path / "restart.db"
    migrate(db)
    url = f"sqlite:///{db.as_posix()}"
    app = create_app(Settings(url, auth_secret="s" * 40))
    create_tenant(app.state.session_factory, "tenant-demo-a", "A")
    create_tenant(app.state.session_factory, "tenant-demo-b", "B")
    create_user(app.state.session_factory, "tenant-demo-a", "rh@a.test", Role.RH, None, PASSWORD)
    create_user(app.state.session_factory, "tenant-demo-b", "rh@b.test", Role.RH, None, PASSWORD)
    aurora = HEADER + "\n" + line() + "\n"
    mar = HEADER + "\n" + line(demand="9", hours="8") + "\n"
    with TestClient(app) as client:
        rh, other = login(client, "tenant-demo-a", "rh@a.test"), login(client, "tenant-demo-b", "rh@b.test")
        first = client.post("/api/imports", json={"team_id": "team-aurora", "filename": "a.csv", "content": aurora}, headers=rh)
        snap_a = client.post(f"/api/imports/{first.json()['import_id']}/confirm", headers=rh).json()["snapshot_id"]
        second = client.post("/api/imports", json={"team_id": "team-mar", "filename": "m.csv", "content": mar}, headers=rh)
        snap_m = client.post(f"/api/imports/{second.json()['import_id']}/confirm", headers=rh).json()["snapshot_id"]
        assert client.get("/api/teams/team-mar/metrics", params={"snapshot_id": snap_a}, headers=rh).status_code == 404
        assert client.get("/api/teams/team-aurora/metrics", params={"snapshot_id": snap_m}, headers=rh).status_code == 404
        opened = client.post("/api/investigations", json={
            "team_id": "team-aurora", "snapshot_id": snap_a, "idempotency_key": "run-restart", "cycle_limit": 3,
        }, headers=rh)
        run_id = opened.json()["run_id"]
        waiting = client.post(f"/api/investigations/{run_id}/advance", headers=rh).json()
        assert waiting["state"] == "WAITING_INPUT" and waiting["forecast"]["status"] == "abstained"
        assert client.get(f"/api/investigations/{run_id}", headers=other).status_code == 404
    app.state.engine.dispose()

    resumed = create_app(Settings(url, auth_secret="s" * 40))
    with TestClient(resumed) as client:
        rh, other = login(client, "tenant-demo-a", "rh@a.test"), login(client, "tenant-demo-b", "rh@b.test")
        state = client.get(f"/api/investigations/{run_id}", headers=rh)
        assert state.json()["state"] == "WAITING_INPUT"
        repeated = client.post("/api/investigations", json={
            "team_id": "team-aurora", "snapshot_id": snap_a, "idempotency_key": "run-restart", "cycle_limit": 3,
        }, headers=rh)
        assert repeated.json()["run_id"] == run_id
        pending = next(item for item in state.json()["report"]["questions"] if item["status"] == "pending")
        answered = client.post(f"/api/investigations/{run_id}/answers", json={
            "question_id": pending["question_id"], "answer": ANSWER, "idempotency_key": "restart-" + pending["question_id"],
        }, headers=rh)
        assert answered.status_code == 200, answered.text
        audit = client.get(f"/api/investigations/{run_id}/audit", headers=rh)
        assert audit.status_code == 200, audit.text
        assert "investigation.create" in {item["action"] for item in audit.json()["items"]}
        assert ANSWER not in audit.text
        assert client.get(f"/api/investigations/{run_id}/audit", headers=other).status_code == 404
        assert client.get("/api/teams/team-aurora/metrics", params={"snapshot_id": snap_a}, headers=other).status_code == 404
    resumed.state.engine.dispose()


def test_revoked_rule_and_infeasible_block_approval(tmp_path):
    db = tmp_path / "revoke.db"
    migrate(db)
    app = create_app(Settings(f"sqlite:///{db.as_posix()}", auth_secret="s" * 40))
    sessions = app.state.session_factory
    create_tenant(sessions, "tenant-demo-a", "A")
    create_tenant(sessions, "tenant-demo-b", "B")
    author = create_user(sessions, "tenant-demo-a", "author@a.test", Role.RH, None, PASSWORD)
    approver = create_user(sessions, "tenant-demo-a", "approver@a.test", Role.RH, None, PASSWORD)
    create_user(sessions, "tenant-demo-a", "gestor@a.test", Role.GESTOR, "team-aurora", PASSWORD)
    create_user(sessions, "tenant-demo-b", "rh@b.test", Role.RH, None, PASSWORD)
    with sessions() as session:
        load_synthetic(session, Principal(author, "tenant-demo-a", (Membership(Role.RH, None),)),
                       Principal(approver, "tenant-demo-a", (Membership(Role.RH, None),)), "tenant-demo-a")
        session.commit()
    with TestClient(app) as client:
        author_headers = login(client, "tenant-demo-a", "author@a.test")
        rh = login(client, "tenant-demo-a", "approver@a.test")
        gestor = login(client, "tenant-demo-a", "gestor@a.test")
        other = login(client, "tenant-demo-b", "rh@b.test")
        created = client.post("/api/imports", json={"team_id": "team-aurora", "filename": "long.csv", "content": weeks(12)}, headers=author_headers)
        snapshot_id = client.post(f"/api/imports/{created.json()['import_id']}/confirm", headers=author_headers).json()["snapshot_id"]
        opened = client.post("/api/investigations", json={
            "team_id": "team-aurora", "snapshot_id": snapshot_id, "idempotency_key": "run-revoke", "cycle_limit": 3,
        }, headers=author_headers)
        run_id = opened.json()["run_id"]
        ready = finish(client, run_id, author_headers)
        assert ready["state"] == "AWAITING_HUMAN"
        items = client.get(f"/api/investigations/{run_id}/scenarios", headers=rh).json()["items"]
        hire = next(item for item in items if item["kind"] == "hire")
        reallocate = next(item for item in items if item["kind"] == "reallocate")
        assert hire["conclusive"] is False
        with Session(app.state.engine) as session:
            scenario = session.get(ScenarioRow, reallocate["scenario_id"])
            scenario.payload = {**scenario.payload, "conclusive": True}
            flag_modified(scenario, "payload")
            simulation = session.scalar(select(SimulationRow).where(SimulationRow.scenario_id == scenario.scenario_id))
            simulation.payload = {**simulation.payload, "status": "infeasible"}
            flag_modified(simulation, "payload")
            review = session.scalar(select(CriticRow).where(CriticRow.scenario_id == scenario.scenario_id))
            review.payload = {**review.payload, "verdict": "noted", "hard_constraint_failed": False}
            flag_modified(review, "payload")
            session.commit()
        infeasible = client.post(f"/api/scenarios/{reallocate['scenario_id']}/decisions", json={
            "decision": "approve", "reason": REASON, "expected_hash": reallocate["content_hash"], "idempotency_key": "approve-infeasible",
        }, headers=rh)
        assert infeasible.status_code == 409 and infeasible.json()["detail"]["code"] == "NOT_CONCLUSIVE"
        # The model's own "conclusive" and "optimal" flags must not bypass
        # the missing independent v4.2 validator evidence.
        with Session(app.state.engine) as session:
            sim = session.scalar(select(SimulationRow).where(SimulationRow.scenario_id == reallocate["scenario_id"]))
            sim.payload = {**sim.payload, "status": "optimal"}
            flag_modified(sim, "payload")
            session.commit()
        bypass = client.post(f"/api/scenarios/{reallocate['scenario_id']}/decisions", json={
            "decision": "approve", "reason": REASON, "expected_hash": reallocate["content_hash"],
            "idempotency_key": "bypass-independent-validation",
        }, headers=rh)
        assert bypass.status_code == 409 and bypass.json()["detail"]["code"] == "NOT_CONCLUSIVE"

        listed = client.get("/api/policies", params={"rule_key": "workweek.max_hours"}, headers=rh).json()["items"]
        chosen = None
        for policy in listed:
            detail = client.get(f"/api/policies/{policy['policy_id']}", headers=rh).json()
            for version in detail["versions"]:
                if version["status"] == "approved" and version["version_id"] in hire["rule_versions"]:
                    chosen = policy["policy_id"], version
        assert chosen is not None
        policy_id, version = chosen
        revoked = client.post(
            f"/api/policies/{policy_id}/versions/{version['version_id']}/revoke",
            json={"expected_revision": version["revision"], "revocation_reason": "fixture sintetica retirada"},
            headers=rh,
        )
        assert revoked.status_code == 200 and revoked.json()["status"] == "revoked"
        blocked = client.post(f"/api/scenarios/{hire['scenario_id']}/decisions", json={
            "decision": "approve", "reason": REASON, "expected_hash": hire["content_hash"], "idempotency_key": "approve-revoked",
        }, headers=rh)
        assert blocked.status_code == 409 and blocked.json()["detail"]["code"] == "MATERIAL_CHANGE"
        rejected = client.post(f"/api/scenarios/{hire['scenario_id']}/decisions", json={
            "decision": "reject", "reason": REASON, "expected_hash": hire["content_hash"], "idempotency_key": "reject-revoked",
        }, headers=rh)
        assert rejected.status_code == 200, rejected.text
        assert client.post(f"/api/scenarios/{hire['scenario_id']}/requisition-drafts", json={"idempotency_key": "draft-revoked"}, headers=rh).status_code == 409

        audit = client.get(f"/api/investigations/{run_id}/audit", headers=rh)
        assert audit.status_code == 200, audit.text
        actions = {item["action"] for item in audit.json()["items"]}
        assert {"investigation.create", "decision.record"} <= actions
        assert ANSWER not in audit.text and REASON not in audit.text
        assert client.get(f"/api/investigations/{run_id}/audit", headers=gestor).status_code == 403
        assert client.get(f"/api/investigations/{run_id}/audit", headers=other).status_code == 404
    app.state.engine.dispose()
