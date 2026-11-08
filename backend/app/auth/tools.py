"""Authorization for agent tools and the worker. Envelope scope is checked, never trusted."""
from backend.app.audit.log import record_event
from backend.app.audit.tracing import normalize_trace_id
from backend.app.auth.dependencies import load_principal
from backend.app.auth.permissions import Permission, Principal

# Operation names passed by backend.app.jobs.engine.MockExecutor. Anything else is denied.
OPERATION_PERMISSIONS: dict[str, Permission] = {
    "create": Permission.INVESTIGATION_RUN,
    "claim": Permission.INVESTIGATION_RUN,
    "heartbeat": Permission.INVESTIGATION_RUN,
    "step": Permission.INVESTIGATION_RUN,
    "answer": Permission.INVESTIGATION_ANSWER,
}


class ToolForbidden(PermissionError):
    code = "FORBIDDEN_SCOPE"


def authorize_tool(principal: Principal, permission: Permission, *, tenant_id: str, team_id: str | None) -> Principal:
    """team_id None asks for a tenant-wide grant."""
    if (not isinstance(principal, Principal) or not isinstance(permission, Permission)
            or not isinstance(tenant_id, str) or tenant_id != principal.tenant_id
            or (team_id is not None and (not isinstance(team_id, str) or not team_id))
            or not principal.can(permission, team_id)):
        raise ToolForbidden("FORBIDDEN_SCOPE")
    return principal


def _trace(scope) -> str | None:
    trace = getattr(scope, "trace_id", None)
    return normalize_trace_id(trace)  # None: record_event uses the current trace


class PrincipalBoundary:
    """IntegrationBoundary for jobs.engine bound to an authenticated identity.

    Rights are reloaded on every call, so disable, logout (token_version), membership
    changes and tenant deactivation stop a long-running worker at its next operation.
    """
    def __init__(self, session_factory, *, user_id: str, tenant_id: str, token_version: int):
        self.sessions = session_factory
        self.user_id, self.tenant_id, self.token_version = user_id, tenant_id, token_version

    @classmethod
    def for_request(cls, request, principal: Principal) -> "PrincipalBoundary":
        """Boundary for the principal authenticated by get_principal in this request."""
        return cls(request.app.state.session_factory, user_id=principal.user_id, tenant_id=principal.tenant_id,
                   token_version=request.state.token_version)

    def _principal(self, session) -> Principal | None:
        return load_principal(session, {"sub": self.user_id, "tid": self.tenant_id, "ver": self.token_version})

    def _check(self, principal, operation: str, scope) -> Permission | None:
        permission = OPERATION_PERMISSIONS.get(operation)
        if principal is None or permission is None:
            raise ToolForbidden("FORBIDDEN_SCOPE")
        authorize_tool(principal, permission, tenant_id=scope.tenant_id, team_id=scope.team_id)
        return permission

    def authorize(self, operation: str, scope) -> None:
        with self.sessions() as session:
            try:
                self._check(self._principal(session), operation, scope)
            except ToolForbidden:
                # Recorded under the bound tenant: the envelope's tenant and team are untrusted.
                permission = OPERATION_PERMISSIONS.get(operation)
                record_event(session, action="authz.denied", outcome="denied", tenant_id=self.tenant_id,
                             actor_user_id=self.user_id,
                             details={"permission": permission.value if permission else None,
                                      "operation": str(operation)[:64]}, trace_id=_trace(scope))
                session.commit()
                raise

    def audit(self, operation: str, scope, run_id: str, version: int) -> None:
        with self.sessions() as session:
            self._check(self._principal(session), operation, scope)
            record_event(session, action=f"job.{operation}", outcome="success", tenant_id=self.tenant_id,
                         actor_user_id=self.user_id, team_id=scope.team_id, resource_type="run",
                         resource_id=run_id, details={"version": version}, trace_id=_trace(scope))
            session.commit()
