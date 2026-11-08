"""Tenants, users and memberships. Membership team_id NULL means tenant-wide."""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, validates

from backend.app.core.database import Base


def utcnow():
    return datetime.now(timezone.utc)


def normalize_email(value: str) -> str:
    return value.strip().lower()


class Tenant(Base):
    __tablename__ = "tenants"
    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),)
    user_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(128), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Bumped on logout/disable: every token issued with an older version is rejected.
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    @validates("email")
    def _normalize(self, key, value):
        return normalize_email(value)


class MembershipRow(Base):
    __tablename__ = "memberships"
    # NULL team_id never conflicts in UNIQUE; duplicates are also rejected in code.
    __table_args__ = (UniqueConstraint("user_id", "role", "team_id", name="uq_memberships_user_role_team"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.user_id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    team_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
