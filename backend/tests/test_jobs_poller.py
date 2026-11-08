from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker

from backend.app.jobs.engine import Conflict, MockExecutor, Scope, now
from backend.app.jobs.models import Checkpoint, JobsBase, Run
from backend.app.jobs.poller import poll_once


class Boundary:
    def authorize(self, operation, scope):
        if scope.tenant_id == "denied":
            raise PermissionError()


@pytest.fixture
def setup(tmp_path):
    db = create_engine(f"sqlite:///{tmp_path / 'poll.db'}")
    JobsBase.metadata.create_all(db)
    sessions = sessionmaker(db, expire_on_commit=False)
    return MockExecutor(sessions, Boundary()), sessions, Scope("tenant", "team", "snapshot", "trace")


def make(worker, scope, key, **options):
    args = dict(max_steps=6, max_cost=0, max_attempts=2,
                deadline=datetime.now(timezone.utc) + timedelta(hours=1))
    args.update(options)
    return worker.create(scope, key, **args)


def test_limit_scope_authorization_and_selection(setup):
    worker, sessions, scope = setup
    ids = [make(worker, scope, str(i)) for i in range(3)]
    others = [make(worker, Scope(*parts), f"other-{i}") for i, parts in enumerate([
        ("other", "team", "snapshot", "trace"), ("tenant", "other", "snapshot", "trace"),
        ("tenant", "team", "other", "trace"), ("tenant", "team", "snapshot", "other")])]
    result = poll_once(worker, scope, limit=2)
    assert (result.selected, result.claimed, result.stepped) == (2, 2, 2)
    with sessions() as s:
        assert sorted(s.get(Run, i).steps for i in ids) == [0, 1, 1]
        assert all(s.get(Run, i).steps == 0 for i in others)
    with pytest.raises(PermissionError): poll_once(worker, Scope("denied", "team", "snapshot", "trace"))
    for limit in (0, 101, True):
        with pytest.raises(ValueError): poll_once(worker, scope, limit=limit)


def test_waiting_terminal_and_deadline_with_live_lease(setup):
    worker, sessions, scope = setup
    waiting = make(worker, scope, "waiting")
    terminal = make(worker, scope, "terminal", max_steps=1)
    for _ in range(3): poll_once(worker, scope)
    with sessions() as s:
        assert s.get(Run, waiting).state == "WAITING_INPUT"
        assert s.get(Run, terminal).state == "FAILED"
    leased = make(worker, scope, "leased")
    token = worker.claim(leased, scope)
    assert poll_once(worker, scope).selected == 0
    with sessions.begin() as s:
        s.execute(update(Run).where(Run.id.in_([waiting, leased, terminal])).values(deadline=now() - timedelta(seconds=1)))
    result = poll_once(worker, scope)
    assert (result.selected, result.claimed, result.stepped) == (2, 0, 0)
    with sessions() as s:
        assert s.get(Run, waiting).failure == "DEADLINE"
        assert s.get(Run, leased).failure == "DEADLINE"
        assert s.get(Run, terminal).failure != "DEADLINE"
    assert not worker.heartbeat(leased, scope, token)
    assert poll_once(worker, scope).selected == 0


def test_restart_retry_limit_and_no_duplicate_step(setup):
    worker, sessions, scope = setup
    run_id = make(worker, scope, "retry", max_attempts=2)
    old = worker.claim(run_id, scope)
    assert poll_once(worker, scope).selected == 0
    with sessions.begin() as s:
        s.execute(update(Run).where(Run.id == run_id).values(lease_until=now() - timedelta(seconds=1)))
    restarted = MockExecutor(sessions, Boundary())
    assert poll_once(restarted, scope).stepped == 1
    with pytest.raises(Conflict): worker.step(run_id, scope, old)
    with sessions() as s:
        assert s.get(Run, run_id).steps == 1
        assert [c.state for c in s.scalars(select(Checkpoint).where(Checkpoint.run_id == run_id).order_by(Checkpoint.version))] == ["CREATED", "VALIDATING"]
    exhausted = make(worker, scope, "exhausted", max_attempts=1)
    worker.claim(exhausted, scope)
    with sessions.begin() as s:
        s.execute(update(Run).where(Run.id == exhausted).values(lease_until=now() - timedelta(seconds=1)))
    poll_once(restarted, scope)
    with sessions() as s:
        assert s.get(Run, exhausted).failure == "ATTEMPTS_OR_DEADLINE"
