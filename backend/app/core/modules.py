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


# Add domain modules here as they are implemented. The future worker owns execution.
DOMAIN_MODULES: tuple[DomainModule, ...] = ()


def collect_jobs(modules: tuple[DomainModule, ...]) -> dict[str, JobDefinition]:
    jobs = {}
    for module in modules:
        for job in module.jobs:
            if job.name in jobs:
                raise ValueError(f"Duplicate job name: {job.name}")
            jobs[job.name] = job
    return jobs
