"""Durable mock-only worker. No public endpoints or real node execution."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import math
from typing import Protocol
from uuid import uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError

from .models import Answer, Checkpoint, Run


class Conflict(ValueError):
    pass


@dataclass(frozen=True)
class Scope:
    tenant_id: str
    team_id: str
    snapshot_id: str
    trace_id: str


class IntegrationBoundary(Protocol):
    """Future P2 adapter: authorization must raise on denial; audit belongs to caller.

    This prototype does not provide or assert authorization/audit. Never use with
    real data until the common component and transactional audit are integrated.
    """
    def authorize(self, operation: str, scope: Scope) -> None: ...
    def audit(self, operation: str, scope: Scope, run_id: str, version: int) -> None: ...


def now():
    # SQLite stores naive datetimes. Values represent UTC on every supported DB.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def valid_id(value):
    return isinstance(value, str) and bool(value) and value == value.strip() and len(value) <= 200


class MockExecutor:
    """Only synthetic nodes. No scenarios, integrations, or external effects."""
    def __init__(self, session_factory, boundary: IntegrationBoundary):
        self.sessions = session_factory
        self.boundary = boundary

    def create(self, scope: Scope, key: str, *, max_steps: int, max_cost: float,
               deadline: datetime, max_attempts: int = 3) -> str:
        if not all(valid_id(x) for x in (scope.tenant_id, scope.team_id, scope.snapshot_id, scope.trace_id, key)):
            raise ValueError("invalid identifier")
        if (not isinstance(max_steps, int) or isinstance(max_steps, bool) or max_steps < 1 or
            not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or max_attempts < 1 or
            not math.isfinite(max_cost) or max_cost < 0 or deadline.tzinfo is None):
            raise ValueError("invalid limits")
        deadline = deadline.astimezone(timezone.utc).replace(tzinfo=None)
        self.boundary.authorize("create", scope)
        fp = digest([scope.snapshot_id, scope.trace_id, max_steps, max_cost, deadline.isoformat(), max_attempts])
        with self.sessions() as s:
            existing = s.scalar(select(Run).where(Run.tenant_id == scope.tenant_id, Run.team_id == scope.team_id, Run.idempotency_key == key))
            if existing:
                if existing.fingerprint != fp: raise Conflict("idempotency key reused")
                return existing.id
            run = Run(id=str(uuid4()), tenant_id=scope.tenant_id, team_id=scope.team_id, snapshot_id=scope.snapshot_id,
                      trace_id=scope.trace_id, idempotency_key=key, fingerprint=fp, state="CREATED", version=0,
                      steps=0, max_steps=max_steps, cost=0, max_cost=max_cost, deadline=deadline, attempts=0, max_attempts=max_attempts)
            s.add(run)
            s.add(Checkpoint(run_id=run.id, version=0, state="CREATED", payload={"mock": True}, created_at=now()))
            try: s.commit()
            except IntegrityError:
                s.rollback()
                existing = s.scalar(select(Run).where(Run.tenant_id == scope.tenant_id, Run.team_id == scope.team_id, Run.idempotency_key == key))
                if not existing or existing.fingerprint != fp: raise Conflict("idempotency key reused")
                return existing.id
            return run.id

    def _run(self, s, run_id, scope, operation):
        self.boundary.authorize(operation, scope)
        run = s.get(Run, run_id)
        if not run or (run.tenant_id, run.team_id, run.snapshot_id, run.trace_id) != (scope.tenant_id, scope.team_id, scope.snapshot_id, scope.trace_id):
            raise Conflict("run unavailable")
        return run

    def _expire(self, s, run, instant):
        """Commit expiry before reporting a conflict; CAS prevents stale writers."""
        version = run.version + 1
        result = s.execute(update(Run).where(
            Run.id == run.id, Run.version == run.version, Run.deadline <= instant,
            Run.state.not_in(("FAILED", "BLOCKED", "COMPLETED")),
        ).values(state="FAILED", failure="DEADLINE", version=version,
                 lease_token=None, lease_until=None, question_id=None))
        if result.rowcount:
            s.add(Checkpoint(run_id=run.id, version=version, state="FAILED",
                             payload={"mock": True, "reason": "DEADLINE"}, created_at=instant))
            s.commit()
            return True
        s.rollback()
        return False

    def claim(self, run_id: str, scope: Scope, lease_seconds: int = 30) -> str | None:
        if not isinstance(lease_seconds, int) or isinstance(lease_seconds, bool) or lease_seconds < 1: raise ValueError("invalid lease")
        with self.sessions() as s:
            run = self._run(s, run_id, scope, "claim")
            instant = now()
            if instant >= run.deadline and run.state not in ("FAILED", "BLOCKED", "COMPLETED"):
                self._expire(s, run, instant)
                return None
            if run.state not in ("CREATED", "VALIDATING", "INVESTIGATING", "PLANNING") or (run.lease_until and run.lease_until > instant): return None
            token = str(uuid4())
            if run.attempts >= run.max_attempts:
                next_version = run.version + 1
                result = s.execute(update(Run).where(Run.id == run_id, Run.version == run.version,
                    or_(Run.lease_until.is_(None), Run.lease_until <= instant)).values(state="FAILED", failure="ATTEMPTS_OR_DEADLINE", version=next_version, lease_token=None, lease_until=None))
                if result.rowcount:
                    s.add(Checkpoint(run_id=run_id, version=next_version, state="FAILED", payload={"mock": True, "reason": "ATTEMPTS_OR_DEADLINE"}, created_at=instant))
                s.commit()
                return None
            result = s.execute(update(Run).where(Run.id == run_id, Run.version == run.version,
                or_(Run.lease_until.is_(None), Run.lease_until <= instant)).values(lease_token=token, lease_until=instant + timedelta(seconds=lease_seconds), attempts=Run.attempts + 1, version=Run.version + 1))
            s.commit()
            return token if result.rowcount else None

    def heartbeat(self, run_id: str, scope: Scope, token: str, lease_seconds: int = 30) -> bool:
        if not isinstance(lease_seconds, int) or isinstance(lease_seconds, bool) or lease_seconds < 1: raise ValueError("invalid lease")
        with self.sessions() as s:
            self._run(s, run_id, scope, "heartbeat")
            instant = now()
            result = s.execute(update(Run).where(Run.id == run_id, Run.lease_token == token, Run.lease_until > instant,
                                                  Run.deadline > instant).values(lease_until=instant + timedelta(seconds=lease_seconds)))
            s.commit()
            return bool(result.rowcount)

    def step(self, run_id: str, scope: Scope, token: str) -> str:
        with self.sessions() as s:
            run = self._run(s, run_id, scope, "step")
            instant = now()
            if run.lease_token != token or not run.lease_until or run.lease_until <= instant: raise Conflict("lease expired")
            if run.steps >= run.max_steps or instant >= run.deadline or run.cost > run.max_cost:
                target, question, reason = "FAILED", None, "LIMIT_REACHED"
            elif run.state == "CREATED": target, question, reason = "VALIDATING", None, None
            elif run.state == "VALIDATING": target, question, reason = "INVESTIGATING", None, None
            elif run.state == "INVESTIGATING": target, question, reason = "WAITING_INPUT", str(uuid4()), None
            elif run.state == "PLANNING": target, question, reason = "BLOCKED", None, "REAL_NODES_UNAVAILABLE"
            else: raise Conflict("state cannot execute")
            version = run.version + 1
            result = s.execute(update(Run).where(Run.id == run_id, Run.version == run.version, Run.lease_token == token,
                Run.lease_until > instant).values(state=target, version=version, steps=Run.steps + 1,
                question_id=question, failure=reason, lease_token=None, lease_until=None, attempts=0))
            if not result.rowcount: s.rollback(); raise Conflict("stale lease")
            s.add(Checkpoint(run_id=run_id, version=version, state=target, payload={"mock": True, "question_id": question, "reason": reason}, created_at=instant))
            s.commit()
            return target

    def answer(self, run_id: str, scope: Scope, *, question_id: str, expected_version: int, key: str, answer: str) -> int:
        if not all(valid_id(x) for x in (question_id, key)) or not isinstance(answer, str) or not answer.strip(): raise ValueError("invalid answer")
        fp = digest([question_id, expected_version, answer])
        with self.sessions() as s:
            run = self._run(s, run_id, scope, "answer")
            prior = s.scalar(select(Answer).where(Answer.run_id == run_id, Answer.idempotency_key == key))
            if prior:
                if prior.fingerprint != fp: raise Conflict("idempotency key reused")
                return prior.version
            instant = now()
            if instant >= run.deadline and run.state not in ("FAILED", "BLOCKED", "COMPLETED"):
                self._expire(s, run, instant)
                raise Conflict("deadline expired")
            if run.state != "WAITING_INPUT" or run.version != expected_version or run.question_id != question_id: raise Conflict("stale question or version")
            # Queue a mock continuation; its next step blocks before any real node.
            version = run.version + 1
            result = s.execute(update(Run).where(Run.id == run_id, Run.state == "WAITING_INPUT", Run.version == expected_version,
                Run.question_id == question_id, Run.deadline > instant).values(state="PLANNING", version=version, question_id=None, failure=None))
            if not result.rowcount: s.rollback(); raise Conflict("stale question or version")
            s.add(Answer(run_id=run_id, idempotency_key=key, fingerprint=fp, version=version))
            s.add(Checkpoint(run_id=run_id, version=version, state="PLANNING", payload={"mock": True, "resumed": True}, created_at=now()))
            s.commit()
            return version

