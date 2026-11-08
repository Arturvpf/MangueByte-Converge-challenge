"""Per-request trace id: accepted from X-Trace-Id when well formed, else generated.

The id lives in a contextvar so audit events, logs and tool responses in the
same request share it. Starlette copies the context into threadpool calls, so
sync endpoints and dependencies see it too.
"""
import re
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import uuid4

from starlette.responses import PlainTextResponse

TRACE_HEADER = "X-Trace-Id"
TRACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9._~-]{1,128}$")
_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)


def new_trace_id() -> str:
    return uuid4().hex


def valid_trace_id(value) -> bool:
    return isinstance(value, str) and TRACE_ID_PATTERN.fullmatch(value) is not None


def current_trace_id() -> str:
    """Trace id of the current request/job; a fresh id outside any context."""
    return _trace_id.get() or new_trace_id()


@contextmanager
def use_trace_id(trace_id: str | None = None):
    """Bind a trace id outside HTTP (jobs, workers, scripts); yields the id."""
    trace_id = trace_id if valid_trace_id(trace_id) else new_trace_id()
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
        trace_id = incoming if valid_trace_id(incoming) else new_trace_id()
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
