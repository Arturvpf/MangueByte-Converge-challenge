"""Lifecycle: transitions, four-eyes, stale revision, and audit."""
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.audit.models import AuditEvent
from backend.app.auth.cli import create_tenant, create_user
from backend.app.auth.permissions import Membership, Permission, Principal, Role
from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.policies.models import PolicyVersion
from backend.app.policies.schemas import PolicyCreate, VersionCreate, VersionUpdate
from backend.app.policies.service import (
    IdempotencyConflict, InvalidTransition, PolicyForbidden, StaleRevision, approve_version, create_policy,
    create_version, reject_version, revoke_version, submit_version, update_draft,
)

ROOT = Path(__file__).resolve().parents[2]
SOURCE = "SINTÉTICO — não é regra jurídica validada"


def alembic(db):
    subprocess.run([sys.executable, "-m", "alembic", "-c", "backend/alembic.ini", "upgrade", "head"], cwd=ROOT,
                   env={**os.environ, "DATABASE_URL": f"sqlite:///{db.as_posix()}"}, check=True, capture_output=True)


def principal(user_id, role=Role.RH, team_id=None):
    return Principal(user_id, "tenant-demo-a", (Membership(role, team_id),))


def draft(**overrides):
    payload = {
        "rule_key": "workweek.max_hours", "team_id": None, "employee_category": None, "title": "Jornada sintética",
        "parameters": {"max_hours": "8"}, "source_kind": "sintetico", "source_reference": SOURCE,
        "valid_from": date(2026, 1, 1), "valid_until": None,
    }
    payload.update(overrides)
    return PolicyCreate.model_validate(payload)


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "policies.db"
    alembic(path)
    app = create_app(Settings(f"sqlite:///{path.as_posix()}", auth_secret="s" * 40))
    sessions = app.state.session_factory
    create_tenant(sessions, "tenant-demo-a", "Demo A")
    author = create_user(sessions, "tenant-demo-a", "author@demo.test", Role.RH, None, "synthetic-test-password")
    approver = create_user(sessions, "tenant-demo-a", "approver@demo.test", Role.RH, None, "synthetic-test-password")
    team_rh = create_user(sessions, "tenant-demo-a", "team@demo.test", Role.RH, "team-1", "synthetic-test-password")
    gestor = create_user(sessions, "tenant-demo-a", "gestor@demo.test", Role.GESTOR, "team-1", "synthetic-test-password")
    yield sessions, principal(author), principal(approver), principal(team_rh, team_id="team-1"), principal(gestor, Role.GESTOR, "team-1")
    app.state.engine.dispose()


def events(session, action):
    return list(session.scalars(select(AuditEvent).where(AuditEvent.action == action)))


def test_lifecycle_four_eyes_stale_revision_and_audit(db):
    sessions, author, approver, team_rh, gestor = db
    with sessions() as session:
        with pytest.raises(PolicyForbidden):
            create_policy(session, gestor, draft())
        session.rollback()
        assert events(session, "policy.create") == []

        policy, version = create_policy(session, author, draft(), "create-1")
        again, _ = create_policy(session, author, draft(), "create-1")
        assert again.policy_id == policy.policy_id
        with pytest.raises(IdempotencyConflict):
            create_policy(session, author, draft(title="Outra"), "create-1")
        session.rollback()
        policy, version = create_policy(session, author, draft(), "create-2")
        session.commit()
        policy_id, version_id = policy.policy_id, version.version_id

    with sessions() as session:
        submit_version(session, author, version_id, 0)
        session.commit()
        with pytest.raises(PolicyForbidden):
            approve_version(session, author, version_id, 1, "parecer-sintetico")
        session.rollback()
        assert events(session, "policy.version.approve") == []
        with pytest.raises(StaleRevision):
            submit_version(session, author, version_id, 0)
        session.rollback()
        assert len(events(session, "policy.version.submit")) == 1

        with pytest.raises(PolicyForbidden):
            approve_version(session, author, version_id, 1, "parecer-sintetico")
        with pytest.raises(PolicyForbidden):
            approve_version(session, team_rh, version_id, 1, "parecer-sintetico")
        session.rollback()
        approve_version(session, approver, version_id, 1, "parecer-sintetico")
        session.commit()
        stored = session.get(PolicyVersion, version_id)
        assert stored.status == "approved" and stored.parameters["max_hours"] == "8"
        assert len(events(session, "policy.version.approve")) == 1

        copied, new_version = create_version(session, author, policy_id, VersionCreate.model_validate({
            "copy_from_version_id": version_id, "parameters": None, "source_kind": None,
            "source_reference": None, "valid_from": None, "valid_until": None,
        }))
        session.commit()
        assert new_version.version == 2 and new_version.status == "draft"
        assert session.get(PolicyVersion, version_id).status == "approved"
        assert session.get(PolicyVersion, version_id).parameters["max_hours"] == "8"

        update_draft(session, author, new_version.version_id, VersionUpdate.model_validate({
            "expected_revision": 0, "parameters": {"max_hours": "7"}, "source_kind": "sintetico",
            "source_reference": SOURCE, "valid_from": date(2026, 2, 1), "valid_until": None,
        }))
        session.commit()
        assert session.get(PolicyVersion, version_id).parameters["max_hours"] == "8"
        assert session.get(PolicyVersion, new_version.version_id).parameters["max_hours"] == "7"

        submit_version(session, author, new_version.version_id, 1)
        reject_version(session, approver, new_version.version_id, 2, "ajuste sintetico")
        session.commit()
        assert session.get(PolicyVersion, new_version.version_id).status == "draft"

        submit_version(session, author, new_version.version_id, 3)
        approve_version(session, approver, new_version.version_id, 4, "parecer-sintetico-2")
        revoke_version(session, approver, version_id, 2, "substituida no teste")
        session.commit()
        assert session.get(PolicyVersion, version_id).status == "revoked"
        assert session.get(PolicyVersion, new_version.version_id).status == "approved"
        assert events(session, "policy.version.revoke")
