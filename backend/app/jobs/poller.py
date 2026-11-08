"""Bounded, explicitly scoped polling for the synthetic executor only."""
from dataclasses import dataclass

from sqlalchemy import and_, or_, select

from .engine import Conflict, MockExecutor, Scope, now, valid_id
from .models import Run


@dataclass(frozen=True)
class PollResult:
    selected: int
    claimed: int
    stepped: int


def poll_once(executor: MockExecutor, scope: Scope, *, limit: int = 10,
              lease_seconds: int = 30) -> PollResult:
    """Attempt at most one mock step per selected run; caller schedules polling.

    The caller supplies the entire trusted scope, including snapshot and trace.
    No tenant enumeration or identity construction is performed here.
    """
    if not all(valid_id(x) for x in (scope.tenant_id, scope.team_id, scope.snapshot_id, scope.trace_id)):
        raise ValueError("invalid scope")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise ValueError("invalid limit")
    if not isinstance(lease_seconds, int) or isinstance(lease_seconds, bool) or lease_seconds < 1:
        raise ValueError("invalid lease")
    executor.boundary.authorize("poll", scope)
    instant = now()
    with executor.sessions() as s:
        ids = list(s.scalars(select(Run.id).where(
            Run.tenant_id == scope.tenant_id, Run.team_id == scope.team_id,
            Run.snapshot_id == scope.snapshot_id, Run.trace_id == scope.trace_id,
            Run.state.in_(("CREATED", "VALIDATING", "INVESTIGATING", "PLANNING", "WAITING_INPUT")),
            or_(Run.deadline <= instant, and_(
                Run.state.in_(("CREATED", "VALIDATING", "INVESTIGATING", "PLANNING")),
                or_(Run.lease_until.is_(None), Run.lease_until <= instant))),
        ).order_by(Run.deadline, Run.id).limit(limit)))
    claimed = stepped = 0
    for run_id in ids:
        token = executor.claim(run_id, scope, lease_seconds)
        if token is None:
            continue
        claimed += 1
        try:
            executor.step(run_id, scope, token)
        except Conflict:
            # A concurrent claimant or deadline may invalidate this lease.
            continue
        stepped += 1
    return PollResult(len(ids), claimed, stepped)
