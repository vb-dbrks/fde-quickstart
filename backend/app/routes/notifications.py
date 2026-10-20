from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.deps import SessionDep
from app.notifications import service
from app.permissions.deps import CurrentPrincipal
from app.schemas import MarkedRead, NotificationList, NotificationOut

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
def list_notifications(
    principal: CurrentPrincipal,
    session: SessionDep,
    unread_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> NotificationList:
    items = service.list_notifications(
        session, principal.email, unread_only=unread_only, limit=limit
    )
    return NotificationList(
        items=[NotificationOut.model_validate(item) for item in items],
        unread_count=service.unread_count(session, principal.email),
    )


@router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_read(notification_id: int, principal: CurrentPrincipal, session: SessionDep) -> None:
    if not service.mark_read(session, principal.email, notification_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    session.commit()


@router.post("/read-all")
def mark_all_read(principal: CurrentPrincipal, session: SessionDep) -> MarkedRead:
    updated = service.mark_all_read(session, principal.email)
    session.commit()
    return MarkedRead(updated=updated)
