"""FastAPI application factory."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.app.core.config import Settings
from backend.app.audit.tracing import TraceIdMiddleware
from backend.app.core.database import make_database
from backend.app.core.modules import DOMAIN_MODULES, DomainModule, collect_jobs


def create_app(settings: Settings | None = None, modules: tuple[DomainModule, ...] | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings.from_env()
    modules = modules if modules is not None else DOMAIN_MODULES
    jobs = collect_jobs(modules)
    engine, sessions = make_database(settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        engine.dispose()

    app = FastAPI(title="Alinia API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = sessions
    app.state.jobs = jobs
    app.add_middleware(TraceIdMiddleware)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # FastAPI's default 422 echoes the submitted value ("input", "ctx"), which
        # would return passwords and personal data. Report only where and why.
        # Do not reflect attacker-controlled field names or validator messages.
        sources = {"body", "query", "path", "header", "cookie"}
        errors = [{"type": "validation_error", "loc": [loc[0]] if loc and loc[0] in sources else [],
                   "msg": "Invalid request"} for e in exc.errors() for loc in [e.get("loc", ())]]
        return JSONResponse(status_code=422, content={"detail": errors})

    @app.get("/health", tags=["health"])
    def health():
        return {"status": "ok"}

    for module in modules:
        for router in module.routers:
            app.include_router(router)
    prototype = Path(__file__).resolve().parents[2] / "src"
    if prototype.is_dir():
        app.mount("/prototype", StaticFiles(directory=prototype), name="prototype")
    return app
