"""Append-only snapshots. Payload holds the complete version, not live references."""
from datetime import datetime, timezone
from sqlalchemy import JSON, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from backend.app.core.database import Base

class DataSnapshot(Base):
    __tablename__ = 'data_snapshots'
    __table_args__ = (UniqueConstraint('tenant_id', 'team_id', 'snapshot_id', name='uq_data_snapshot_scope'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    team_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    snapshot_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
