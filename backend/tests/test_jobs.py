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


def test_claim_expires_waiting_input(setup):
    w, sessions, scope = setup
    run_id, _ = create(w, scope)
    for _ in range(3): step(w, run_id, scope)
    with sessions.begin() as s:
        s.execute(update(Run).where(Run.id == run_id).values(deadline=now() - timedelta(seconds=1)))
    assert w.claim(run_id, scope) is None
    with sessions() as s:
        run = s.get(Run, run_id)
        assert run.state == "FAILED" and run.failure == "DEADLINE" and run.question_id is None
        assert s.scalar(select(Checkpoint).where(Checkpoint.run_id == run_id, Checkpoint.version == run.version)).state == "FAILED"


def test_claim_expires_live_lease_and_invalidates_token(setup):
    w, sessions, scope = setup
    run_id, _ = create(w, scope)
    token = w.claim(run_id, scope)
    with sessions.begin() as s:
        s.execute(update(Run).where(Run.id == run_id).values(deadline=now() - timedelta(seconds=1)))
    assert w.claim(run_id, scope) is None
    assert not w.heartbeat(run_id, scope, token)
    with pytest.raises(Conflict): w.step(run_id, scope, token)
    with sessions() as s:
        run = s.get(Run, run_id)
        assert run.state == "FAILED" and run.lease_token is None and run.lease_until is None
        assert s.scalar(select(Checkpoint).where(Checkpoint.run_id == run_id, Checkpoint.version == run.version)).state == "FAILED"


def test_expired_answer_commits_failure_and_prior_replay_still_works(setup):
    w, sessions, scope = setup
    run_id, _ = create(w, scope)
    for _ in range(3): step(w, run_id, scope)
    with sessions() as s:
        run = s.get(Run, run_id)
        version, question = run.version, run.question_id
    with sessions.begin() as s:
        s.execute(update(Run).where(Run.id == run_id).values(deadline=now() - timedelta(seconds=1)))
    with pytest.raises(Conflict, match="deadline expired"):
        w.answer(run_id, scope, question_id=question, expected_version=version, key="new", answer="x")
    with sessions() as s:
        run = s.get(Run, run_id)
        assert run.state == "FAILED" and run.failure == "DEADLINE"
        assert s.scalar(select(Checkpoint).where(Checkpoint.run_id == run_id, Checkpoint.version == run.version)).state == "FAILED"
    other = Scope("tenant", "other", "snapshot", "trace")
    run_id, _ = create(w, other)
    for _ in range(3): step(w, run_id, other)
    with sessions() as s:
        run = s.get(Run, run_id)
        version, question = run.version, run.question_id
    accepted = w.answer(run_id, other, question_id=question, expected_version=version, key="accepted", answer="x")
    with sessions.begin() as s:
        s.execute(update(Run).where(Run.id == run_id).values(deadline=now() - timedelta(seconds=1)))
    assert w.answer(run_id, other, question_id=question, expected_version=version, key="accepted", answer="x") == accepted


def test_steps_use_stateless_langgraph_and_resume_from_sql(setup, monkeypatch):
    from backend.app.jobs import engine as jobs_engine
    from backend.app.jobs.graph import MOCK_GRAPH

    w, sessions, scope = setup
    assert MOCK_GRAPH.checkpointer is None
    invocations = []
    original = MOCK_GRAPH.invoke

    def record(input, *args, **kwargs):
        result = original(input, *args, **kwargs)
        invocations.append((input["state"], result["target"]))
        return result

    monkeypatch.setattr(MOCK_GRAPH, "invoke", record)
    run_id, _ = create(w, scope)
    assert step(w, run_id, scope) == "VALIDATING"
    # A new executor has no in-memory continuation; it reads the committed row.
    resumed = MockExecutor(sessions, Boundary())
    assert step(resumed, run_id, scope) == "INVESTIGATING"
    assert step(resumed, run_id, scope) == "WAITING_INPUT"
    with sessions() as s:
        run = s.get(Run, run_id)
        version, question = run.version, run.question_id
    resumed.answer(run_id, scope, question_id=question, expected_version=version, key="a", answer="x")
    assert step(MockExecutor(sessions, Boundary()), run_id, scope) == "BLOCKED"
    assert invocations == [("CREATED", "VALIDATING"), ("VALIDATING", "INVESTIGATING"),
                           ("INVESTIGATING", "WAITING_INPUT"), ("PLANNING", "BLOCKED")]


def test_lease_expiring_during_graph_cannot_commit(setup, monkeypatch):
    from backend.app.jobs import engine as jobs_engine

    w, sessions, scope = setup
    run_id, _ = create(w, scope)
    token = w.claim(run_id, scope)
    with sessions() as s:
        lease_until = s.get(Run, run_id).lease_until
    times = iter([lease_until - timedelta(microseconds=1), lease_until])
    monkeypatch.setattr(jobs_engine, "now", lambda: next(times))
    with pytest.raises(Conflict, match="stale lease"):
        w.step(run_id, scope, token)
    with sessions() as s:
        assert s.get(Run, run_id).state == "CREATED"
        assert len(s.scalars(select(Checkpoint).where(Checkpoint.run_id == run_id)).all()) == 1
