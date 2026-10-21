from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from backend.api.deps import SessionDep
from backend.auth.deps import CurrentPrincipal
from backend.domain.schemas import MarkedRead, NotificationList, NotificationOut
from backend.services import notifications as service

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
async def list_notifications(
    principal: CurrentPrincipal,
    db: SessionDep,
    unread_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> NotificationList:
    items = await service.list_notifications(
        db, principal.email, unread_only=unread_only, limit=limit
    )
    return NotificationList(
        items=[NotificationOut.model_validate(item) for item in items],
        unread_count=await service.unread_count(db, principal.email),
    )


@router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(notification_id: int, principal: CurrentPrincipal, db: SessionDep) -> None:
    if not await service.mark_read(db, principal.email, notification_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    await db.commit()


@router.post("/read-all")
async def mark_all_read(principal: CurrentPrincipal, db: SessionDep) -> MarkedRead:
    updated = await service.mark_all_read(db, principal.email)
    await db.commit()
    return MarkedRead(updated=updated)
