"""Per-request trace id: accepted from X-Trace-Id when well formed, else generated.

The id lives in a contextvar so audit events, logs and tool responses in the
same request share it. Starlette copies the context into threadpool calls, so
sync endpoints and dependencies see it too.

Only opaque ids are accepted (32 hex chars, as uuid4().hex or a W3C trace-id,
or a dashed UUID), stored as 32 lowercase hex. Free text could carry names or
CPFs into the audit trace_id column, which the details sanitizer never sees.
"""
import re
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import uuid4

from starlette.responses import PlainTextResponse

TRACE_HEADER = "X-Trace-Id"
TRACE_ID_PATTERN = re.compile(r"^(?:[0-9a-f]{32}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$",
                              re.IGNORECASE)
_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)


def new_trace_id() -> str:
    return uuid4().hex


def normalize_trace_id(value) -> str | None:
    """Canonical 32 lowercase hex, or None if the value is not an opaque id."""
    if not isinstance(value, str) or TRACE_ID_PATTERN.fullmatch(value) is None:
        return None
    value = value.replace("-", "").lower()
    return None if value == "0" * 32 else value


def valid_trace_id(value) -> bool:
    """True only for an id already in canonical form."""
    return normalize_trace_id(value) == value


def current_trace_id() -> str:
    """Trace id of the current request/job; a fresh id outside any context."""
    return _trace_id.get() or new_trace_id()


@contextmanager
def use_trace_id(trace_id: str | None = None):
    """Bind a trace id outside HTTP (jobs, workers, scripts); yields the id."""
    trace_id = normalize_trace_id(trace_id) or new_trace_id()
    token = _trace_id.set(trace_id)
    try:
        yield trace_id
    finally:
        _trace_id.reset(token)


class TraceIdMiddleware:
    """Pure ASGI middleware; echoes the id on every HTTP response, errors included."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        incoming = next((v.decode("latin-1") for k, v in scope.get("headers", ()) if k.lower() == b"x-trace-id"), None)
        trace_id = normalize_trace_id(incoming) or new_trace_id()
        scope.setdefault("state", {})["trace_id"] = trace_id
        header = (b"x-trace-id", trace_id.encode())
        started = False

        async def send_with_trace(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                headers = [h for h in message.get("headers", ()) if h[0].lower() != header[0]]
                message = {**message, "headers": headers + [header]}
            await send(message)

        token = _trace_id.set(trace_id)
        try:
            await self.app(scope, receive, send_with_trace)
        except Exception:
            # Unhandled error: answer here so the 500 carries the id, then re-raise
            # for server logging; the outer handler sees an already started response.
            if scope["type"] == "http" and not started:
                await PlainTextResponse("Internal Server Error", 500, {TRACE_HEADER: trace_id})(scope, receive, send)
            raise
        finally:
            _trace_id.reset(token)
