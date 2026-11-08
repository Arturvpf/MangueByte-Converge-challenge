"""P2-01 end to end: migrated DB, real login, data scope by role/tenant, audit correlation."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session

from backend.app.audit.models import AuditEvent
from backend.app.auth.cli import create_tenant, create_user
from backend.app.auth.permissions import Role
from backend.app.core.config import Settings
from backend.app.data.repository import DataRepository, DataScope
from backend.app.data.schemas import SnapshotData
from backend.app.main import create_app

ROOT = Path(__file__).resolve().parents[2]
PASSWORD = 'synthetic-test-password'  # test-only value


def alembic(db, *args):
    subprocess.run([sys.executable, '-m', 'alembic', '-c', 'backend/alembic.ini', *args], cwd=ROOT,
                   env={**os.environ, 'DATABASE_URL': f'sqlite:///{db.as_posix()}'}, check=True, capture_output=True)


def snapshot(name):
    raw = json.loads((ROOT / f'backend/fixtures/contracts/{name}.json').read_text(encoding='utf-8'))
    c, d = raw['capacity'], raw['demand']
    skills = sorted({r['skill_id'] for r in c['rows']} | {r['skill_id'] for r in d['records']})
    shifts = sorted({r['shift_id'] for r in c['rows']})
    return SnapshotData.model_validate_json(json.dumps({
        'team': {'id': c['team_id'], 'name': name}, 'skills': [{'id': i, 'name': i} for i in skills], 'roles': [],
        'shifts': [{'id': i, 'name': i} for i in shifts], 'source': {'kind': 'synthetic', 'reference': name, 'version': '1'},
        'capacity': c, 'demand': d}))


@pytest.fixture
def env(tmp_path):
    db = tmp_path / 'p2.db'
    alembic(db, 'upgrade', 'head')
    app = create_app(Settings(f'sqlite:///{db.as_posix()}', auth_secret='s' * 40))
    sessions = app.state.session_factory
    a, b = snapshot('aurora'), snapshot('mar')
    with Session(app.state.engine) as session:
        for s in (a, b):
            DataRepository(session, DataScope(s.capacity.tenant_id, frozenset([s.team.id]))).add_snapshot(s)
        session.commit()
    ta, tb = a.capacity.tenant_id, b.capacity.tenant_id
    create_tenant(sessions, ta, 'Demo A')
    create_tenant(sessions, tb, 'Demo B')
    users = {
        'gestor_a': create_user(sessions, ta, 'gestor@a.test', Role.GESTOR, a.team.id, PASSWORD),
        'gestor_other': create_user(sessions, ta, 'outro@a.test', Role.GESTOR, 'team-other', PASSWORD),
        'rh_a': create_user(sessions, ta, 'rh@a.test', Role.RH, None, PASSWORD),
        'admin_a': create_user(sessions, ta, 'admin@a.test', Role.ADMIN, None, PASSWORD),
        'rh_b': create_user(sessions, tb, 'rh@b.test', Role.RH, None, PASSWORD),
    }
    with TestClient(app) as client:
        def login(tenant, email):
            r = client.post('/api/auth/login', json={'tenant_id': tenant, 'email': email, 'password': PASSWORD})
            assert r.status_code == 200, r.text
            return {'Authorization': f"Bearer {r.json()['access_token']}"}
        yield client, app, db, a, b, login, users
    app.state.engine.dispose()


def test_data_scope_follows_verified_identity(env):
    client, app, db, a, b, login, users = env
    ta, tb = a.capacity.tenant_id, b.capacity.tenant_id
    path_a = f'/api/teams/{a.team.id}/snapshots/{a.capacity.data_snapshot_id}'

    assert client.get(path_a).status_code == 401
    assert client.get(path_a, headers={'Authorization': 'Bearer forged'}).status_code == 401

    gestor = login(ta, 'gestor@a.test')
    assert [t['id'] for t in client.get('/api/teams', headers=gestor).json()] == [a.team.id]
    assert client.get(path_a, headers=gestor).status_code == 200

    other = login(ta, 'outro@a.test')  # same tenant, different team
    assert client.get('/api/teams', headers=other).json() == []
    assert client.get(path_a, headers=other).status_code == 403

    rh = login(ta, 'rh@a.test')  # tenant-wide RH
    assert [t['id'] for t in client.get('/api/teams', headers=rh).json()] == [a.team.id]

    rh_b = login(tb, 'rh@b.test')  # other tenant never sees tenant A, even with the same team id in the path
    assert [t['id'] for t in client.get('/api/teams', headers=rh_b).json()] == [b.team.id]
    assert client.get(path_a, headers=rh_b).status_code == 403

    admin = login(ta, 'admin@a.test')  # admin manages access, not planning data
    assert client.get('/api/teams', headers=admin).status_code == 403

    # A user cannot log in to another tenant with the same credentials.
    r = client.post('/api/auth/login', json={'tenant_id': tb, 'email': 'gestor@a.test', 'password': PASSWORD})
    assert r.status_code == 401


def test_audit_correlates_trace_and_stays_in_tenant(env):
    client, app, db, a, b, login, users = env
    ta, tb = a.capacity.tenant_id, b.capacity.tenant_id
    # Denial raised by the common component (permission missing). Team-level denials
    # inside the data handlers (ForbiddenScope) are instrumented by P1 in its module.
    admin = login(ta, 'admin@a.test')
    r = client.get('/api/teams', headers={**admin, 'X-Trace-Id': 'a100000000000000000000000000000d'})
    assert r.status_code == 403 and r.headers['x-trace-id'] == 'a100000000000000000000000000000d'

    events = client.get('/api/audit', params={'trace_id': 'a100000000000000000000000000000d'}, headers=admin).json()['items']
    assert [(e['action'], e['outcome'], e['actor_user_id']) for e in events] == [('authz.denied', 'denied', users['admin_a'])]
    assert 'admin@a.test' not in json.dumps(events)

    rh_b = login(tb, 'rh@b.test')
    assert client.get('/api/audit', params={'trace_id': 'a100000000000000000000000000000d'}, headers=rh_b).json()['items'] == []
    gestor = login(ta, 'gestor@a.test')
    assert client.get('/api/audit', headers=gestor).status_code == 403

    with Session(app.state.engine) as session:
        logins = session.scalars(select(AuditEvent).where(AuditEvent.action == 'auth.login')).all()
        assert logins and all(e.outcome == 'success' for e in logins)
        assert not any('@' in json.dumps(e.details) for e in logins)


def test_audit_table_is_append_only_in_database(env):
    client, app, db, a, b, login, users = env
    engine = create_engine(f'sqlite:///{db.as_posix()}')
    with engine.connect() as conn:
        assert conn.execute(text('select count(*) from audit_events')).scalar_one() > 0
        with pytest.raises(DatabaseError):
            conn.execute(text("update audit_events set outcome = 'success'"))
        conn.rollback()
        with pytest.raises(DatabaseError):
            conn.execute(text('delete from audit_events'))
    engine.dispose()


def test_database_rejects_invalid_memberships(env):
    client, app, db, a, b, login, users = env
    engine = create_engine(f'sqlite:///{db.as_posix()}')
    insert = text('insert into memberships (tenant_id, user_id, role, team_id) values (:t, :u, :r, :team)')
    for role, team in (('gestor', None), ('owner', 'x'), ('rh', '  ')):
        with engine.connect() as conn:
            with pytest.raises(DatabaseError):
                conn.execute(insert, {'t': a.capacity.tenant_id, 'u': users['gestor_a'], 'r': role, 'team': team})
    engine.dispose()


def test_validation_errors_never_echo_submitted_values(env):
    # P1 review: the default 422 returned the password in "input".
    client, app, db, a, b, login, users = env
    secret = 'valor-secreto-que-nao-pode-voltar'
    admin = login(a.capacity.tenant_id, 'admin@a.test')
    responses = [
        client.post('/api/auth/login', json={'tenant_id': a.capacity.tenant_id, 'password': secret}),
        client.post('/api/admin/users', json={'password': secret, 'memberships': []}, headers=admin),
        client.post('/api/admin/users', json={'email': secret, 'password': secret, 'memberships': [], 'x': secret}, headers=admin),
        client.get('/api/audit', params={'team_id': f'{secret}@mail.test'}, headers=admin),
    ]
    for r in responses:
        assert r.status_code == 422 and secret not in r.text
        assert all(set(e) == {'type', 'loc', 'msg'} for e in r.json()['detail'])
    assert ['body', 'email'] in [e['loc'] for e in responses[0].json()['detail']]


def test_audit_columns_never_store_unverified_free_text(env):
    # P1 review: team_id and X-Trace-Id values reached audit columns; empty team_id gave 500.
    client, app, db, a, b, login, users = env
    admin = login(a.capacity.tenant_id, 'admin@a.test')
    assert client.get('/api/audit', params={'team_id': ''}, headers=admin).status_code == 422
    assert client.get('/api/audit', params={'trace_id': 'joao.silva'}, headers=admin).status_code == 422
    for value in ('123.456.789-09', 'joao.silva', 'Maria Souza', 'a' * 32 + 'z'):
        r = client.get('/api/audit', params={'team_id': 'joao.silva'}, headers={**admin, 'X-Trace-Id': value})
        assert r.status_code == 200 and r.headers['x-trace-id'] != value
    dashed = 'A1B2C3D4-0000-4000-8000-00000000000F'
    assert client.get('/health', headers={'X-Trace-Id': dashed}).headers['x-trace-id'] == dashed.replace('-', '').lower()
    with Session(app.state.engine) as session:
        stored = session.scalars(select(AuditEvent)).all()
        assert not any(e.team_id == 'joao.silva' for e in stored)
        assert all(len(e.trace_id) == 32 and set(e.trace_id) <= set('0123456789abcdef') for e in stored)
    # Admin cannot grant a team id that is free text either.
    r = client.post('/api/admin/users', json={'email': 'novo@a.test', 'password': PASSWORD,
                                              'memberships': [{'role': 'gestor', 'team_id': 'joao.silva@empresa.com'}]}, headers=admin)
    assert r.status_code == 422 and 'joao.silva@empresa.com' not in r.text


def test_audit_rows_cannot_be_replaced_or_upserted(env):
    # P1 review: INSERT OR REPLACE overwrote an existing event in SQLite.
    client, app, db, a, b, login, users = env
    engine = create_engine(f'sqlite:///{db.as_posix()}')
    with engine.connect() as conn:
        row = conn.execute(text('select id, occurred_at, action from audit_events limit 1')).mappings().one()
        forged = {'id': row['id'], 'o': row['occurred_at']}
        cols = "(id, occurred_at, trace_id, tenant_id, actor_type, action, outcome, details) values (:id, :o, 'x', 't', 'user', 'forged.event', 'success', '{}')"
        for statement in (f'insert or replace into audit_events {cols}', f'replace into audit_events {cols}',
                          f"insert into audit_events {cols} on conflict(id) do update set action = 'forged.event'"):
            with pytest.raises(DatabaseError):
                conn.execute(text(statement), forged)
            conn.rollback()
        assert conn.execute(text('select action from audit_events where id = :id'), forged).scalar_one() == row['action']
    engine.dispose()


def test_migration_downgrade_removes_p2_tables(tmp_path):
    db = tmp_path / 'down.db'
    alembic(db, 'upgrade', 'head')
    alembic(db, 'downgrade', '0002')
    engine = create_engine(f'sqlite:///{db.as_posix()}')
    names = set(inspect(engine).get_table_names())
    assert 'data_snapshots' in names and not names & {'tenants', 'users', 'memberships', 'audit_events'}
    engine.dispose()
