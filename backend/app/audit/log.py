"""Record and query audit events. Recording joins the caller's transaction."""
import base64
import json
import re
from datetime import datetime, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from backend.app.audit.models import ACTOR_TYPES, OUTCOMES, AuditEvent
from backend.app.audit.sanitize import sanitize_details
from backend.app.audit.tracing import current_trace_id, valid_trace_id

ACTION_PATTERN = re.compile(r"^[a-z][a-z0-9_.]{0,63}$")
MAX_LIMIT = 500


class InvalidCursor(ValueError):
    pass


def _text(name, value, size, required=False):
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value or len(value) > size:
        raise ValueError(f"{name} must be a non-empty string of at most {size} chars")
    return value


def as_utc(value: datetime) -> datetime:
    # Naive values are UTC (SQLite returns them naive).
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def record_event(session: Session, *, action: str, outcome: str, tenant_id: str,
                 actor_user_id: str | None = None, actor_type: str = "user",
                 team_id: str | None = None, resource_type: str | None = None,
                 resource_id: str | None = None, details: dict | None = None,
                 trace_id: str | None = None) -> AuditEvent:
    """Add one event and flush; the caller commits with its business change.

    Identifiers only: resource_id and details must not carry personal data.
    """
    if not isinstance(action, str) or not ACTION_PATTERN.fullmatch(action):
        raise ValueError("invalid audit action")
    if outcome not in OUTCOMES:
        raise ValueError("invalid audit outcome")
    if actor_type not in ACTOR_TYPES:
        raise ValueError("invalid audit actor_type")
    trace_id = current_trace_id() if trace_id is None else trace_id
    if not valid_trace_id(trace_id):
        raise ValueError("invalid trace_id")
    item = AuditEvent(
        occurred_at=datetime.now(timezone.utc), trace_id=trace_id,
        tenant_id=_text("tenant_id", tenant_id, 128, required=True), team_id=_text("team_id", team_id, 128),
        actor_type=actor_type, actor_user_id=_text("actor_user_id", actor_user_id, 36),
        action=action, outcome=outcome, resource_type=_text("resource_type", resource_type, 64),
        resource_id=_text("resource_id", resource_id, 128), details=sanitize_details(details))
    session.add(item)
    session.flush()
    return item


def encode_cursor(item: AuditEvent) -> str:
    raw = json.dumps([as_utc(item.occurred_at).isoformat(), item.id]).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        at, ident = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        if not isinstance(ident, str) or len(ident) > 36:
            raise ValueError
        return as_utc(datetime.fromisoformat(at)), ident
    except Exception as exc:
        raise InvalidCursor("invalid audit cursor") from exc


def query_events(session: Session, *, tenant_id: str, team_ids: frozenset[str] | None,
                 trace_id: str | None = None, action: str | None = None,
                 resource_type: str | None = None, resource_id: str | None = None,
                 since: datetime | None = None, until: datetime | None = None,
                 limit: int = 100, cursor: str | None = None) -> tuple[list[AuditEvent], str | None]:
    """Newest first, ordered by (occurred_at, id). team_ids None = whole tenant;
    a set restricts to those teams and excludes tenant-level (team_id NULL) events."""
    _text("tenant_id", tenant_id, 128, required=True)
    if team_ids is not None and not team_ids:
        return [], None
    limit = max(1, min(int(limit), MAX_LIMIT))
    stmt = select(AuditEvent).where(AuditEvent.tenant_id == tenant_id)
    if team_ids is not None:
        stmt = stmt.where(AuditEvent.team_id.in_(sorted(team_ids)))
    for column, value in ((AuditEvent.trace_id, trace_id), (AuditEvent.action, action),
                          (AuditEvent.resource_type, resource_type), (AuditEvent.resource_id, resource_id)):
        if value is not None:
            stmt = stmt.where(column == value)
    if since is not None:
        stmt = stmt.where(AuditEvent.occurred_at >= as_utc(since))
    if until is not None:
        stmt = stmt.where(AuditEvent.occurred_at < as_utc(until))
    if cursor is not None:
        at, ident = decode_cursor(cursor)
        stmt = stmt.where(or_(AuditEvent.occurred_at < at, and_(AuditEvent.occurred_at == at, AuditEvent.id < ident)))
    rows = list(session.scalars(stmt.order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc()).limit(limit + 1)))
    if len(rows) <= limit:
        return rows, None
    return rows[:limit], encode_cursor(rows[limit - 1])
