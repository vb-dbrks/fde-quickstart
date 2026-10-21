from fastapi import APIRouter, Request, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend.api.deps import SessionDep
from backend.domain.schemas import HealthOut

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(db: SessionDep, request: Request, response: Response) -> HealthOut:
    """Database reachability, plus which agent runner serves each run kind."""
    runtime = getattr(request.app.state, "agent_runtime", None)
    agent = {"transport": request.app.state.settings.agent_transport}
    if runtime is not None:
        agent["runners"] = runtime.runner_names
    try:
        await db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthOut(status="degraded", database="error", agent=agent)
    return HealthOut(status="ok", database="ok", agent=agent)
