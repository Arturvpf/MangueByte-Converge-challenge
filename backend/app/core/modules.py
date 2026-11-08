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


from backend.app.data.api import router as data_router

DOMAIN_MODULES: tuple[DomainModule, ...] = (DomainModule(routers=(data_router,)),)


def collect_jobs(modules: tuple[DomainModule, ...]) -> dict[str, JobDefinition]:
    jobs = {}
    for module in modules:
        for job in module.jobs:
            if job.name in jobs:
                raise ValueError(f"Duplicate job name: {job.name}")
            jobs[job.name] = job
    return jobs
