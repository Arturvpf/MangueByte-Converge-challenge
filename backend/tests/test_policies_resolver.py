"""Which approved rule applies on a date, including pins and tampered hashes."""
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from backend.app.auth.cli import create_tenant, create_user
from backend.app.auth.permissions import Membership, Principal, Role
from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.policies.resolver import resolve, resolve_pinned
from backend.app.policies.schemas import PolicyCreate, VersionCreate
from backend.app.policies.service import approve_version, create_policy, create_version, submit_version

ROOT = Path(__file__).resolve().parents[2]
SOURCE = "SINTÉTICO — não é regra jurídica validada"


def _app(tmp_path, name):
    path = tmp_path / name
    subprocess.run([sys.executable, "-m", "alembic", "-c", "backend/alembic.ini", "upgrade", "head"], cwd=ROOT,
                   env={**os.environ, "DATABASE_URL": f"sqlite:///{path.as_posix()}"}, check=True, capture_output=True)
    app = create_app(Settings(f"sqlite:///{path.as_posix()}", auth_secret="s" * 40))
    create_tenant(app.state.session_factory, "tenant-demo-a", "A")
    create_tenant(app.state.session_factory, "tenant-demo-b", "B")
    author = create_user(app.state.session_factory, "tenant-demo-a", "a@demo.test", Role.RH, None, "synthetic-test-password")
    approver = create_user(app.state.session_factory, "tenant-demo-a", "b@demo.test", Role.RH, None, "synthetic-test-password")
    other = create_user(app.state.session_factory, "tenant-demo-b", "c@demo.test", Role.RH, None, "synthetic-test-password")
    return app, Principal(author, "tenant-demo-a", (Membership(Role.RH, None),)), Principal(approver, "tenant-demo-a", (Membership(Role.RH, None),)), Principal(other, "tenant-demo-b", (Membership(Role.RH, None),))


def _publish(session, author, approver, **overrides):
    payload = {
        "rule_key": "workweek.max_hours", "team_id": None, "employee_category": None, "title": "Sintética",
        "parameters": {"max_hours": "8"}, "source_kind": "sintetico", "source_reference": SOURCE,
        "valid_from": date(2026, 1, 1), "valid_until": date(2026, 6, 1),
    }
    payload.update(overrides)
    policy, version = create_policy(session, author, PolicyCreate.model_validate(payload))
    submit_version(session, author, version.version_id, 0)
    approve_version(session, approver, version.version_id, 1, "parecer-sintetico")
    session.commit()
    return policy, version


def _ask(session, on, keys=("workweek.max_hours",), team="team-1", category=None, tenant="tenant-demo-a"):
    return resolve(session, tenant_id=tenant, team_id=team, employee_category=category, on_date=on,
                   rule_keys=list(keys), data_snapshot_id="snap-1")


def test_resolution_cases(tmp_path):
    app, author, approver, other = _app(tmp_path, "resolve.db")
    engine = create_engine(app.state.settings.database_url)
    with Session(engine) as session:
        missing = _ask(session, date(2026, 3, 1))
        assert missing.items[0].reason == "missing" and missing.complete is False

        policy, version = _publish(session, author, approver)
        draft_only = _ask(session, date(2026, 3, 1))
        assert draft_only.items[0].status == "resolved"
        assert _ask(session, date(2026, 6, 1)).items[0].reason == "missing"
        assert _ask(session, date(2025, 12, 31)).items[0].reason == "missing"

        _, second = create_version(session, author, policy.policy_id, VersionCreate.model_validate({
            "copy_from_version_id": None, "parameters": {"max_hours": "7"}, "source_kind": "sintetico",
            "source_reference": SOURCE, "valid_from": date(2026, 3, 1), "valid_until": date(2026, 4, 1),
        }))
        submit_version(session, author, second.version_id, 0)
        approve_version(session, approver, second.version_id, 1, "parecer-2")
        session.commit()
        assert _ask(session, date(2026, 3, 15)).items[0].reason == "conflict"
        assert _ask(session, date(2026, 3, 15), keys=("rest.weekly_min_days",)).items[0].reason == "missing"

        _publish(session, author, approver, rule_key="workday.max_hours", team_id="team-1", title="Diaria equipe",
                 parameters={"max_hours": "6", "requires_collective_agreement": False}, valid_until=None)
        _publish(session, author, approver, rule_key="workday.max_hours", title="Diaria empresa",
                 parameters={"max_hours": "9", "requires_collective_agreement": True}, valid_until=None)
        picked = _ask(session, date(2026, 3, 1), keys=("workday.max_hours",))
        assert picked.items[0].status == "resolved" and picked.items[0].parameters.max_hours == 6

        _publish(session, author, approver, rule_key="contract.modality", employee_category="estagiario",
                 title="Modalidade", parameters={
                     "modality": "estagio", "allowed": True, "max_duration_days": None, "requires_legal_review": True,
                 }, valid_until=None)
        scoped = _ask(session, date(2026, 3, 1), keys=("contract.modality",), category="estagiario")
        assert scoped.items[0].status == "resolved"
        assert _ask(session, date(2026, 3, 1), keys=("contract.modality",)).items[0].reason == "missing"

        session.execute(text("update policy_versions set status = 'revoked' where version_id = :id"), {"id": version.version_id})
        session.commit()
        assert _ask(session, date(2026, 2, 1)).items[0].reason == "missing"

        pinned = resolve_pinned(session, tenant_id="tenant-demo-a", team_id="team-1", on_date=date(2026, 3, 1),
                                version_ids=[version.version_id], data_snapshot_id="snap-1")
        assert pinned.items[0].reason == "pinned_revoked" and pinned.items[0].parameters is None
        foreign = resolve_pinned(session, tenant_id="tenant-demo-b", team_id="team-1", on_date=date(2026, 3, 1),
                                 version_ids=[version.version_id], data_snapshot_id="snap-1")
        assert foreign.items[0].reason == "pinned_not_found" and foreign.items[0].rule_key is None

        live = _ask(session, date(2026, 3, 1), keys=("workday.max_hours",))
        session.execute(text("update policy_versions set content_hash = :h where version_id = :id"),
                        {"h": "b" * 64, "id": live.items[0].version_id})
        session.commit()
        assert _ask(session, date(2026, 3, 1), keys=("workday.max_hours",)).items[0].reason == "hash_mismatch"

        first = _ask(session, date(2026, 5, 1), keys=("workday.max_hours", "contract.modality"), category="estagiario")
        second_pass = _ask(session, date(2026, 5, 1), keys=("workday.max_hours", "contract.modality"), category="estagiario")
        assert first.model_dump(mode="json") == second_pass.model_dump(mode="json")
    engine.dispose()
    app.state.engine.dispose()
