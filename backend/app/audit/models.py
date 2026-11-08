"""Append-only audit events, correlated by trace_id and scoped by tenant/team.

Details are sanitized before storage (see sanitize.py): no personal data, raw
prompts or free text. Events serve accountability, never disciplinary use.
"""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, DateTime, String, event
from sqlalchemy.orm import Mapped, Session, mapped_column

from backend.app.core.database import Base

ACTOR_TYPES = frozenset({"user", "system", "agent"})
OUTCOMES = frozenset({"success", "denied", "failure", "error"})


class AuditImmutableError(RuntimeError):
    pass


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True,
                                                  default=lambda: datetime.now(timezone.utc))
    trace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    team_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


def _is_audit_dml(state) -> bool:
    table = getattr(state.statement, "table", None)
    return getattr(table, "name", None) == AuditEvent.__tablename__ or \
        any(m.class_ is AuditEvent for m in state.all_mappers)


# ORM-level guard for every Session; database grants/triggers should back it in production.
@event.listens_for(Session, "before_flush")
def _block_audit_changes(session, flush_context, instances):
    for obj in session.deleted:
        if isinstance(obj, AuditEvent):
            raise AuditImmutableError("audit events are append-only")
    for obj in session.dirty:
        if isinstance(obj, AuditEvent) and session.is_modified(obj):
            raise AuditImmutableError("audit events are append-only")


@event.listens_for(Session, "do_orm_execute")
def _block_audit_bulk(state):
    if (state.is_update or state.is_delete) and _is_audit_dml(state):
        raise AuditImmutableError("audit events are append-only")
