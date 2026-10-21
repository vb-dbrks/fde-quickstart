"""REST API, mounted under /api. Interactive docs: /api/docs."""

from fastapi import APIRouter

from backend.api import admin, agent_runs, documents, health, me, notifications, threads

api_router = APIRouter()
for module in (health, me, documents, agent_runs, threads, notifications, admin):
    api_router.include_router(module.router)
