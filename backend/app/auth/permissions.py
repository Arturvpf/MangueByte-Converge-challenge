"""Roles, permissions and the authenticated principal (P2-01).

A Principal is built only from a verified token plus the database. Request
bodies, tool arguments and LLM text never contribute to it.
"""
from dataclasses import dataclass
from enum import Enum

from backend.app.core.ids import valid_id


class Role(str, Enum):
    GESTOR = "gestor"
    RH = "rh"
    ADMIN = "admin"


class Permission(str, Enum):
    DATA_READ = "data:read"
    INVESTIGATION_RUN = "investigation:run"
    INVESTIGATION_ANSWER = "investigation:answer"
    SCENARIO_READ = "scenario:read"
    DECISION_WRITE = "decision:write"
    REQUISITION_DRAFT = "requisition:draft"
    POLICY_READ = "policy:read"
    POLICY_WRITE = "policy:write"
    POLICY_APPROVE = "policy:approve"
    AUDIT_READ = "audit:read"
    USER_MANAGE = "user:manage"


P = Permission
ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    # Operations manager: investigates own teams, never decides.
    Role.GESTOR: frozenset({P.DATA_READ, P.INVESTIGATION_RUN, P.INVESTIGATION_ANSWER, P.SCENARIO_READ, P.POLICY_READ}),
    # HR: the only role that records decisions and requisition drafts (PRD 12, 14).
    Role.RH: frozenset({P.DATA_READ, P.INVESTIGATION_RUN, P.INVESTIGATION_ANSWER, P.SCENARIO_READ, P.DECISION_WRITE,
                        P.REQUISITION_DRAFT, P.POLICY_READ, P.POLICY_WRITE, P.POLICY_APPROVE, P.AUDIT_READ}),
    # Administrator: manages access and reads audit; no planning data by default (minimization).
    Role.ADMIN: frozenset({P.USER_MANAGE, P.AUDIT_READ, P.POLICY_READ}),
}

# Roles that may hold a tenant-wide membership (team_id is None).
TENANT_WIDE_ROLES = frozenset({Role.RH, Role.ADMIN})


@dataclass(frozen=True)
class Membership:
    role: Role
    team_id: str | None  # None = every team of the tenant


@dataclass(frozen=True)
class Principal:
    user_id: str
    tenant_id: str
    memberships: tuple[Membership, ...]

    def has(self, permission: Permission) -> bool:
        """True if any membership grants the permission, for any team."""
        return any(permission in ROLE_PERMISSIONS[m.role] for m in self.memberships)

    def can(self, permission: Permission, team_id: str | None = None) -> bool:
        """Permission on a team; team_id None asks for a tenant-wide grant."""
        return any(
            permission in ROLE_PERMISSIONS[m.role] and (m.team_id is None or m.team_id == team_id)
            for m in self.memberships
        )

    def tenant_wide(self, permission: Permission) -> bool:
        return self.can(permission, None)

    def team_ids(self, permission: Permission) -> frozenset[str]:
        """Teams explicitly granted; check tenant_wide() separately."""
        return frozenset(m.team_id for m in self.memberships
                         if m.team_id is not None and permission in ROLE_PERMISSIONS[m.role])


def check_memberships(memberships) -> None:
    """Grant rules shared by the admin API and CLI. Raises ValueError."""
    seen = set()
    for m in memberships:
        if m.team_id is None and m.role not in TENANT_WIDE_ROLES:
            raise ValueError(f"role {m.role.value} requires team_id")
        if m.team_id is not None and not valid_id(m.team_id):
            raise ValueError("invalid team_id")
        if (m.role, m.team_id) in seen:
            raise ValueError("duplicate membership")
        seen.add((m.role, m.team_id))
