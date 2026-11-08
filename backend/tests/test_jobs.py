from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker

from backend.app.jobs.engine import Conflict, MockExecutor, Scope, now
from backend.app.jobs.models import Checkpoint, JobsBase, Run


class Boundary:
    def authorize(self, operation, scope):
        if scope.tenant_id == "denied": raise PermissionError()
    def audit(self, operation, scope, run_id, version):
        raise AssertionError("audit is not integrated")


@pytest.fixture
def setup(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'jobs.db'}")
    JobsBase.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    return MockExecutor(sessions, Boundary()), sessions, Scope("tenant", "team", "snapshot", "trace")


def create(worker, scope, **kwargs):
    opts = dict(max_steps=6, max_cost=0, deadline=datetime.now(timezone.utc) + timedelta(hours=1), max_attempts=2)
    opts.update(kwargs)
    return worker.create(scope, "create-key", **opts), opts


def step(worker, run_id, scope):
    token = worker.claim(run_id, scope)
    assert token
    return worker.step(run_id, scope, token)


def test_pause_resume_idempotency_and_block(setup):
    w, sessions, scope = setup
    run_id, opts = create(w, scope)
    assert w.create(scope, "create-key", **opts) == run_id
    with pytest.raises(Conflict): w.create(scope, "create-key", **{**opts, "max_steps": 8})
    assert [step(w, run_id, scope) for _ in range(3)] == ["VALIDATING", "INVESTIGATING", "WAITING_INPUT"]
    assert w.claim(run_id, scope) is None
    with sessions() as s:
        run = s.get(Run, run_id)
        version, question = run.version, run.question_id
    with pytest.raises(Conflict): w.answer(run_id, scope, question_id=question, expected_version=version - 1, key="a", answer="x")
    v = w.answer(run_id, scope, question_id=question, expected_version=version, key="a", answer="x")
    assert w.answer(run_id, scope, question_id=question, expected_version=version, key="a", answer="x") == v
    with pytest.raises(Conflict): w.answer(run_id, scope, question_id=question, expected_version=version, key="a", answer="different")
    assert step(w, run_id, scope) == "BLOCKED"
    with sessions() as s:
        checkpoints = s.scalars(select(Checkpoint).where(Checkpoint.run_id == run_id).order_by(Checkpoint.version)).all()
        assert [c.state for c in checkpoints] == ["CREATED", "VALIDATING", "INVESTIGATING", "WAITING_INPUT", "PLANNING", "BLOCKED"]
        assert all(c.payload["mock"] for c in checkpoints)


def test_lease_recovery_and_stale_worker(setup):
    w, sessions, scope = setup
    run_id, _ = create(w, scope)
    old = w.claim(run_id, scope)
    assert w.claim(run_id, scope) is None
    assert w.heartbeat(run_id, scope, old)
    with sessions.begin() as s:
        s.execute(update(Run).where(Run.id == run_id).values(lease_until=now() - timedelta(seconds=1)))
    new = w.claim(run_id, scope)
    assert new and new != old
    assert not w.heartbeat(run_id, scope, old)
    with pytest.raises(Conflict): w.step(run_id, scope, old)
    assert w.step(run_id, scope, new) == "VALIDATING"


def test_attempt_and_step_limits(setup):
    w, sessions, scope = setup
    run_id, _ = create(w, scope, max_attempts=1)
    assert w.claim(run_id, scope)
    with sessions.begin() as s: s.execute(update(Run).where(Run.id == run_id).values(lease_until=now() - timedelta(seconds=1)))
    assert w.claim(run_id, scope) is None
    with sessions() as s: assert s.get(Run, run_id).state == "FAILED"
    other = Scope("tenant", "team2", "snapshot", "trace")
    run_id, _ = create(w, other, max_steps=1)
    assert step(w, run_id, other) == "VALIDATING"
    assert step(w, run_id, other) == "FAILED"


def test_scope_and_deadline(setup):
    w, sessions, scope = setup
    run_id, _ = create(w, scope, deadline=datetime.now(timezone.utc) - timedelta(seconds=1))
    with pytest.raises(Conflict): w.claim(run_id, Scope("tenant", "other", "snapshot", "trace"))
    with pytest.raises(PermissionError): w.claim(run_id, Scope("denied", "team", "snapshot", "trace"))
    assert w.claim(run_id, scope) is None
    with sessions() as s: assert s.get(Run, run_id).state == "FAILED"
