"""REST API, mounted under /api. Interactive docs: /api/docs."""

from fastapi import APIRouter

from app.routes import admin, agents, health, me, notes, notifications

api_router = APIRouter()
for module in (health, me, notes, notifications, admin, agents):
    api_router.include_router(module.router)
