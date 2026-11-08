"""Regression: Jira source checkpoints must never cross team boundaries."""
import json
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.auth.cli import create_tenant, create_user
from backend.app.auth.permissions import Role
from backend.app.core.config import Settings
from backend.app.flow.models import JiraCheckpoint
from backend.app.main import create_app
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
PASSWORD = "synthetic-test-password"


def migrate(path):
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "backend/alembic.ini", "upgrade", "head"],
        cwd=ROOT,
        env={**os.environ, "DATABASE_URL": f"sqlite:///{path.as_posix()}"},
        check=True, capture_output=True,
    )


def test_same_jira_issue_in_two_teams_is_not_deduplicated_across_teams(tmp_path):
    path = tmp_path / "scopes.db"
    migrate(path)
    app = create_app(Settings(f"sqlite:///{path.as_posix()}", auth_secret="s" * 40))
    create_tenant(app.state.session_factory, "tenant-a", "A")
    create_user(app.state.session_factory, "tenant-a", "rh@a.test", Role.RH, None, PASSWORD)
    with TestClient(app) as client:
        resp = client.post("/api/auth/login", json={
            "tenant_id": "tenant-a", "email": "rh@a.test", "password": PASSWORD,
        })
        assert resp.status_code == 200
        headers = {"Authorization": "Bearer " + resp.json()["access_token"]}
        first = client.post("/api/imports/jira", json={"team_id": "team-a", "fixture": "issues"}, headers=headers)
        second = client.post("/api/imports/jira", json={"team_id": "team-b", "fixture": "issues"}, headers=headers)
        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text
        assert first.json()["duplicated"] is False
        assert second.json()["duplicated"] is False
        assert first.json()["snapshot_id"] is not None
        assert second.json()["snapshot_id"] is not None
        assert first.json()["import_id"] != second.json()["import_id"]
        again = client.post("/api/imports/jira", json={"team_id": "team-b", "fixture": "issues"}, headers=headers)
        assert again.status_code == 200 and again.json()["duplicated"] is True
        with Session(app.state.engine) as session:
            checkpoints = list(session.scalars(select(JiraCheckpoint)))
            assert len(checkpoints) == 4
            assert {item.team_id for item in checkpoints} == {"team-a", "team-b"}
            assert {item.source_key for item in checkpoints} == {"fixture:issues"}
    app.state.engine.dispose()


def test_legacy_unscoped_jira_checkpoints_are_quarantined(tmp_path):
    path = tmp_path / "legacy.db"
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "backend/alembic.ini", "upgrade", "0008_scenario_families"],
        cwd=ROOT, env={**os.environ, "DATABASE_URL": f"sqlite:///{path.as_posix()}"},
        check=True, capture_output=True,
    )
    from sqlalchemy import create_engine, text
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO jira_checkpoints (tenant_id, issue_id, snapshot_id) "
            "VALUES ('tenant-a','DEMO-1','unscoped-old-snapshot')"
        ))
    engine.dispose()
    migrate(path)
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    with engine.connect() as connection:
        legacy = connection.execute(text(
            "SELECT snapshot_id FROM jira_checkpoints_legacy_unscoped"
        )).scalar_one()
        active = connection.execute(text(
            "SELECT count(*) FROM jira_checkpoints"
        )).scalar_one()
        assert legacy == "unscoped-old-snapshot"
        assert active == 0
    engine.dispose()
