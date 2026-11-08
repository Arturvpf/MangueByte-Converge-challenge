import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.config import Settings
from backend.app.data.api import get_data_scope
from backend.app.data.repository import DataRepository, DataScope, ForbiddenScope
from backend.app.data.schemas import SnapshotData
from backend.app.main import create_app

ROOT = Path(__file__).resolve().parents[2]

def fixture(name):
    raw = json.loads((ROOT / f'backend/fixtures/contracts/{name}.json').read_text(encoding='utf-8'))
    c, d = raw['capacity'], raw['demand']
    skills = sorted({r['skill_id'] for r in c['rows']} | {r['skill_id'] for r in d['records']})
    shifts = sorted({r['shift_id'] for r in c['rows']})
    value = {'team': {'id': c['team_id'], 'name': name}, 'skills': [{'id': i, 'name': i} for i in skills], 'roles': [], 'shifts': [{'id': i, 'name': i} for i in shifts], 'source': {'kind': 'synthetic', 'reference': name, 'version': '1'}, 'capacity': c, 'demand': d}
    return SnapshotData.model_validate_json(json.dumps(value))

def migrate(db, revision):
    subprocess.run([sys.executable, '-m', 'alembic', '-c', 'backend/alembic.ini', 'upgrade', revision], cwd=ROOT, env={**os.environ, 'DATABASE_URL': f'sqlite:///{db.as_posix()}'}, check=True, capture_output=True)

def test_migration_from_baseline_and_downgrade(tmp_path):
    db = tmp_path / 'data.db'
    migrate(db, '0001')
    engine = create_engine(f'sqlite:///{db.as_posix()}')
    assert 'data_snapshots' not in inspect(engine).get_table_names()
    migrate(db, 'head')
    assert 'data_snapshots' in inspect(engine).get_table_names()
    subprocess.run([sys.executable, '-m', 'alembic', '-c', 'backend/alembic.ini', 'downgrade', '0001'], cwd=ROOT, env={**os.environ, 'DATABASE_URL': f'sqlite:///{db.as_posix()}'}, check=True, capture_output=True)
    assert 'data_snapshots' not in inspect(engine).get_table_names()
    engine.dispose()

def test_repository_and_api_isolation_version_and_origin(tmp_path):
    db = tmp_path / 'data.db'
    migrate(db, 'head')
    app = create_app(Settings(f'sqlite:///{db.as_posix()}'))
    a, b = fixture('aurora'), fixture('mar')
    scope_a = DataScope(a.capacity.tenant_id, frozenset([a.team.id]))
    scope_b = DataScope(b.capacity.tenant_id, frozenset([b.team.id]))
    newer = a.model_dump(mode='json')
    newer['capacity']['data_snapshot_id'] = newer['demand']['data_snapshot_id'] = 'new-version'
    newer['source']['version'] = '2'
    newer['capacity']['rows'][0]['eligible_hours'] = 100.0
    newer = SnapshotData.model_validate_json(json.dumps(newer))
    with Session(app.state.engine) as session:
        DataRepository(session, scope_a).add_snapshot(a)
        DataRepository(session, scope_a).add_snapshot(newer)
        DataRepository(session, scope_b).add_snapshot(b)
        session.commit()
        with pytest.raises(ForbiddenScope):
            DataRepository(session, scope_a).add_snapshot(b)
        with pytest.raises(IntegrityError):
            DataRepository(session, scope_a).add_snapshot(a)
        session.rollback()
    with TestClient(app) as client:
        path = f'/api/teams/{a.team.id}/snapshots/{a.capacity.data_snapshot_id}'
        assert client.get(path).status_code == 403
        app.dependency_overrides[get_data_scope] = lambda: scope_a
        assert [t['id'] for t in client.get('/api/teams').json()] == [a.team.id]
        old = client.get(path)
        assert old.status_code == 200
        assert old.json()['source']['version'] == '1'
        assert old.json()['capacity']['rows'][0]['eligible_hours'] == a.capacity.rows[0].eligible_hours
        assert old.json()['demand']['records'][0]['quantity'] is None
        assert old.json()['capacity']['hours_unit'] == 'hours_per_period'
        assert old.json()['demand']['records'][0]['unit'] == 'cases_per_period'
        assert len(client.get(f'/api/teams/{a.team.id}/snapshots').json()) == 2
        assert client.get(f'/api/teams/{b.team.id}/snapshots/{b.capacity.data_snapshot_id}').status_code == 403
        assert client.get(f'/api/teams/{a.team.id}/snapshots/{b.capacity.data_snapshot_id}').status_code == 404
        # Even with a colliding team ID, tenant filtering prevents access.
        app.dependency_overrides[get_data_scope] = lambda: DataScope('other-tenant', frozenset([a.team.id]))
        assert client.get(path).status_code == 404
        assert client.get('/api/teams').json() == []

def test_reject_personal_extra_and_mismatched_snapshot():
    data = fixture('aurora').model_dump(mode='json')
    bad = copy.deepcopy(data)
    bad['capacity']['rows'][0]['employee_name'] = 'person'
    with pytest.raises(ValidationError):
        SnapshotData.model_validate_json(json.dumps(bad))
    bad = copy.deepcopy(data)
    bad['demand']['data_snapshot_id'] = 'other'
    with pytest.raises(ValidationError):
        SnapshotData.model_validate_json(json.dumps(bad))
