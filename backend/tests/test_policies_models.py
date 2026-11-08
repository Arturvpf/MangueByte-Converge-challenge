"""Policy tables: migration 0005, database CHECKs, and the ORM immutability guard."""
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, delete, inspect, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.auth.models import Tenant, User
from backend.app.policies.models import (
    Policy, PolicyCatalogError, PolicyConflictError, PolicyImmutableError, PolicyVersion,
)

ROOT = Path(__file__).resolve().parents[2]
HASH = "a" * 64
SOURCE = "SINTÉTICO — não é regra jurídica validada"


def alembic(db, *args):
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "backend/alembic.ini", *args],
        cwd=ROOT, env={**os.environ, "DATABASE_URL": f"sqlite:///{db.as_posix()}"}, check=True, capture_output=True,
    )


def engine_for(db):
    return create_engine(f"sqlite:///{db.as_posix()}")


def test_upgrade_head_and_downgrade_to_0004(tmp_path):
    db = tmp_path / "policies.db"
    alembic(db, "upgrade", "head")
    engine = engine_for(db)
    with engine.connect() as conn:
        assert conn.execute(text("select version_num from alembic_version")).scalar_one() == "0007_merge_p1_p2"
    names = set(inspect(engine).get_table_names())
    assert {"policies", "policy_versions", "audit_events", "investigation_runs", "hr_decisions", "requisition_drafts"} <= names
    checks = {item["name"] for item in inspect(engine).get_check_constraints("policy_versions")}
    assert {"ck_policy_versions_status", "ck_policy_versions_version", "ck_policy_versions_validity"} <= checks
    alembic(db, "downgrade", "0005")
    names = set(inspect(engine).get_table_names())
    assert "investigation_runs" not in names and "policies" in names
    alembic(db, "downgrade", "0004")
    with engine.connect() as conn:
        assert conn.execute(text("select version_num from alembic_version")).scalar_one() == "0004"
    names = set(inspect(engine).get_table_names())
    assert "policies" not in names and "policy_versions" not in names and "audit_events" in names
    alembic(db, "upgrade", "head")
    assert "policies" in inspect(engine).get_table_names()
    engine.dispose()


def _seed(session):
    now = datetime.now(timezone.utc)
    session.add(Tenant(tenant_id="tenant-demo-a", name="Demo A", active=True, created_at=now))
    session.add(User(
        user_id="user-author", tenant_id="tenant-demo-a", email="author@demo.test",
        password_hash="not-used", active=True, token_version=0, created_at=now,
    ))
    session.commit()


def _policy(**overrides):
    values = {
        "policy_id": "policy-1", "tenant_id": "tenant-demo-a", "rule_key": "workweek.max_hours",
        "category": "jornada", "team_id": None, "employee_category": None,
        "title": "Jornada semanal sintética", "created_by": "user-author",
    }
    values.update(overrides)
    return Policy(**values)


def _version(**overrides):
    values = {
        "version_id": "version-1", "policy_id": "policy-1", "tenant_id": "tenant-demo-a", "version": 1,
        "status": "approved", "parameters": {"max_hours": "1"}, "source_kind": "sintetico",
        "source_reference": SOURCE, "valid_from": date(2026, 1, 1), "valid_until": None,
        "content_hash": HASH, "revision": 1, "author_user_id": "user-author",
        "legal_review_reference": "parecer-sintetico-1",
    }
    values.update(overrides)
    return PolicyVersion(**values)


def test_checks_reject_invalid_status_and_inverted_validity(tmp_path):
    db = tmp_path / "checks.db"
    alembic(db, "upgrade", "head")
    engine = engine_for(db)
    with Session(engine) as session:
        _seed(session)
        session.add(_policy())
        session.add(_version(status="draft", revision=0, legal_review_reference=None))
        session.commit()

    def insert(**overrides):
        values = {"version_id": "version-bad", "version": 2}
        values.update(overrides)
        with Session(engine) as session:
            session.add(_version(**values))
            session.commit()

    with pytest.raises(IntegrityError, match="ck_policy_versions_status"):
        insert(status="published")
    with pytest.raises(IntegrityError, match="ck_policy_versions_validity"):
        insert(status="draft", valid_from=date(2026, 6, 1), valid_until=date(2026, 1, 1))
    with pytest.raises(IntegrityError, match="ck_policy_versions_validity"):
        insert(status="draft", valid_until=date(2026, 1, 1))
    with pytest.raises(IntegrityError, match="ck_policy_versions_version"):
        insert(status="draft", version=0)
    engine.dispose()


def test_orm_blocks_approved_edits_deletes_and_null_scope_duplicates(tmp_path):
    db = tmp_path / "guard.db"
    alembic(db, "upgrade", "head")
    engine = engine_for(db)
    with Session(engine) as session:
        _seed(session)
        session.add(_policy())
        session.add(_version())
        session.add(_version(
            version_id="version-draft", version=2, status="draft", revision=0, legal_review_reference=None,
        ))
        session.commit()

        approved = session.get(PolicyVersion, "version-1")
        approved.parameters = {"max_hours": "2"}
        with pytest.raises(PolicyImmutableError):
            session.flush()
        session.rollback()
        assert session.get(PolicyVersion, "version-1").parameters["max_hours"] == "1"

        approved = session.get(PolicyVersion, "version-1")
        approved.parameters["max_hours"] = "9"
        with pytest.raises(PolicyImmutableError):
            session.flush()
        session.rollback()
        assert session.get(PolicyVersion, "version-1").parameters["max_hours"] == "1"

        draft = session.get(PolicyVersion, "version-draft")
        draft.parameters = {"max_hours": "4"}
        session.flush()
        assert draft.parameters["max_hours"] == "4"

        approved = session.get(PolicyVersion, "version-1")
        approved.status = "revoked"
        approved.revision = 2
        approved.revocation_reason = "encerrada no teste sintetico"
        session.flush()
        assert approved.status == "revoked"
        assert approved.parameters["max_hours"] == "1"

        session.delete(session.get(PolicyVersion, "version-draft"))
        with pytest.raises(PolicyImmutableError):
            session.flush()
        session.rollback()
        assert session.get(PolicyVersion, "version-draft") is not None

        with pytest.raises(PolicyImmutableError):
            session.execute(delete(PolicyVersion.__table__))
        with pytest.raises(PolicyImmutableError):
            session.execute(update(PolicyVersion).values(parameters={"max_hours": "9"}))

        session.add(_policy(policy_id="policy-2", title="Outra jornada"))
        with pytest.raises(PolicyConflictError):
            session.flush()
        session.rollback()

        session.add(_policy(policy_id="policy-3", rule_key="not.a.rule", category="jornada", team_id="team-1"))
        with pytest.raises(PolicyCatalogError):
            session.flush()
        session.rollback()

        session.add(_version(
            version_id="version-bad", policy_id="policy-1", version=3, status="draft", revision=0,
            legal_review_reference=None, parameters={"max_hours": "0"},
        ))
        with pytest.raises(PolicyCatalogError):
            session.flush()
        session.rollback()

        identity = session.get(Policy, "policy-1")
        identity.rule_key = "workday.max_hours"
        with pytest.raises(PolicyImmutableError):
            session.flush()
        session.rollback()
    engine.dispose()
