"""Synthetic policies load through the service and resolve for both companies."""
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from backend.app.auth.cli import create_tenant, create_user
from backend.app.auth.permissions import Membership, Principal, Role
from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.policies.catalog import CATALOG
from backend.app.policies.fixtures import load_synthetic
from backend.app.policies.resolver import resolve

ROOT = Path(__file__).resolve().parents[2]
PASSWORD = "synthetic-test-password"


def test_synthetic_fixtures_resolve_for_both_companies(tmp_path):
    db = tmp_path / "fixtures.db"
    subprocess.run([sys.executable, "-m", "alembic", "-c", "backend/alembic.ini", "upgrade", "head"], cwd=ROOT,
                   env={**os.environ, "DATABASE_URL": f"sqlite:///{db.as_posix()}"}, check=True, capture_output=True)
    app = create_app(Settings(f"sqlite:///{db.as_posix()}", auth_secret="s" * 40))
    sessions = app.state.session_factory
    for tenant, name in (("tenant-demo-a", "A"), ("tenant-demo-b", "B")):
        create_tenant(sessions, tenant, name)
        author = create_user(sessions, tenant, f"author@{name}.test", Role.RH, None, PASSWORD)
        approver = create_user(sessions, tenant, f"approver@{name}.test", Role.RH, None, PASSWORD)
        with sessions() as session:
            load_synthetic(
                session, Principal(author, tenant, (Membership(Role.RH, None),)),
                Principal(approver, tenant, (Membership(Role.RH, None),)), tenant,
            )
            session.commit()
            resolved = resolve(
                session, tenant_id=tenant, team_id="team-aurora" if tenant.endswith("a") else "team-mar",
                employee_category=None, on_date=date(2026, 6, 1), rule_keys=list(CATALOG), data_snapshot_id="snap-1",
            )
        assert resolved.complete is True
        assert [item.rule_key for item in resolved.items] == list(CATALOG)
        assert all(item.source_reference.startswith("SINTÉTICO") for item in resolved.items)
    with sessions() as session:
        again = resolve(session, tenant_id="tenant-demo-a", team_id="team-aurora", employee_category=None,
                        on_date=date(2026, 6, 1), rule_keys=["workweek.max_hours"], data_snapshot_id="snap-1")
        other = resolve(session, tenant_id="tenant-demo-b", team_id="team-mar", employee_category=None,
                        on_date=date(2026, 6, 1), rule_keys=["workweek.max_hours"], data_snapshot_id="snap-1")
    assert again.items[0].parameters.max_hours == 44
    assert other.items[0].parameters.max_hours == 36
    app.state.engine.dispose()
