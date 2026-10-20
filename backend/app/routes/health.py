from fastapi import APIRouter, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.deps import SessionDep
from app.schemas import HealthOut

router = APIRouter(tags=["health"])


@router.get("/health")
def health(session: SessionDep, response: Response) -> HealthOut:
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthOut(status="degraded", database="error")
    return HealthOut(status="ok", database="ok")
