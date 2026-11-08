import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.config import Settings
from backend.app.data.api import get_data_scope
from backend.app.data.models import DataSnapshot
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
        summaries = client.get(f'/api/teams/{a.team.id}/snapshots').json()
        assert len(summaries) == 2
        assert all(item['created_at'].endswith(('Z', '+00:00')) for item in summaries)
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


def test_mutation_and_corruption_fail_closed(tmp_path):
    db = tmp_path / 'corruption.db'
    migrate(db, 'head')
    app = create_app(Settings(f'sqlite:///{db.as_posix()}'))
    a, b = fixture('aurora'), fixture('mar')
    scope = DataScope(a.capacity.tenant_id, frozenset([a.team.id]))
    with Session(app.state.engine) as session:
        repo = DataRepository(session, scope)
        broken = a.model_copy(deep=True)
        broken.demand.tenant_id = b.capacity.tenant_id
        with pytest.raises(ValidationError):
            repo.add_snapshot(broken)
        assert repo.add_snapshot(a) is None
        session.commit()
        summary = repo.list_snapshots(a.team.id)[0]
        assert not isinstance(summary, DataSnapshot)
        with pytest.raises(Exception):
            summary.snapshot_id = 'changed'
        detached = repo.get_snapshot(a.team.id, a.capacity.data_snapshot_id)
        detached.capacity.tenant_id = 'tampered'
        session.commit()
        assert repo.get_snapshot(a.team.id, a.capacity.data_snapshot_id).capacity.tenant_id == scope.tenant_id
        # Simulate corruption through a privileged SQL client, not the repository.
        session.execute(update(DataSnapshot).values(payload=b.model_dump(mode='json')))
        session.commit()
    app.dependency_overrides[get_data_scope] = lambda: scope
    with TestClient(app) as client:
        for path in ['/api/teams', f'/api/teams/{a.team.id}/snapshots', f'/api/teams/{a.team.id}/snapshots/{a.capacity.data_snapshot_id}']:
            response = client.get(path)
            assert response.status_code == 500
            assert b.capacity.tenant_id not in response.text

@pytest.mark.parametrize('field', ['tenant_id', 'team_id', 'data_snapshot_id'])
@pytest.mark.parametrize('value', ['x' * 129, 'bad/id', '.', '..'])
def test_reject_identifiers_incompatible_with_storage_and_routes(field, value):
    raw = fixture('aurora').model_dump(mode='json')
    raw['capacity'][field] = raw['demand'][field] = value
    if field == 'team_id':
        raw['team']['id'] = value
    with pytest.raises(ValidationError):
        SnapshotData.model_validate_json(json.dumps(raw))


@pytest.mark.parametrize('value', [float('nan'), float('inf'), float('-inf')])
def test_mutated_nonfinite_value_is_not_normalized_to_null(tmp_path, value):
    db = tmp_path / 'nonfinite.db'
    migrate(db, 'head')
    app = create_app(Settings(f'sqlite:///{db.as_posix()}'))
    data = fixture('aurora')
    data.demand.records[0].quantity = value
    with Session(app.state.engine) as session:
        repo = DataRepository(session, DataScope(data.capacity.tenant_id, frozenset([data.team.id])))
        with pytest.raises(ValueError):
            repo.add_snapshot(data)
        assert repo.list_snapshots(data.team.id) == ()
