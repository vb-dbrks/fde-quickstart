"""Explicit example route registration; core routes are always available."""

from fastapi import APIRouter

from backend.api import admin, health, me, notifications


def build_api_router(enabled: frozenset[str]) -> APIRouter:
    router = APIRouter()
    for module in (health, me, notifications, admin):
        router.include_router(module.router)
    if "documents" in enabled:
        from backend.api import agent_runs, documents, feedback, threads
        from backend.examples import proposals

        for module in (documents, agent_runs, threads, feedback, proposals):
            router.include_router(module.router)
    return router
