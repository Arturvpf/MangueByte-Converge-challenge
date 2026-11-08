"""FastAPI application factory."""
from contextlib import asynccontextmanager

from fastapi import FastAPI

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

    @app.get("/health", tags=["health"])
    def health():
        return {"status": "ok"}

    for module in modules:
        for router in module.routers:
            app.include_router(router)
    return app
