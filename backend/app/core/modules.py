"""Explicit domain registration; job declarations are never executed here."""
from dataclasses import dataclass
from typing import Callable

from fastapi import APIRouter


@dataclass(frozen=True)
class JobDefinition:
    name: str
    handler: Callable


@dataclass(frozen=True)
class DomainModule:
    routers: tuple[APIRouter, ...] = ()
    jobs: tuple[JobDefinition, ...] = ()


from backend.app.audit.api import router as audit_router
from backend.app.auth.api import admin_router, router as auth_router
from backend.app.data.api import router as data_router
from backend.app.ingestion.api import router as imports_router
from backend.app.metrics.api import router as metrics_router
from backend.app.policies.api import router as policies_router
from backend.app.workflow.api import router as workflow_router

DOMAIN_MODULES: tuple[DomainModule, ...] = (
    DomainModule(routers=(auth_router, admin_router, audit_router)),  # P2-01
    DomainModule(routers=(data_router, metrics_router, imports_router)),
    DomainModule(routers=(policies_router,)),  # P2-02
    DomainModule(routers=(workflow_router,)),
)


def collect_jobs(modules: tuple[DomainModule, ...]) -> dict[str, JobDefinition]:
    jobs = {}
    for module in modules:
        for job in module.jobs:
            if job.name in jobs:
                raise ValueError(f"Duplicate job name: {job.name}")
            jobs[job.name] = job
    return jobs
