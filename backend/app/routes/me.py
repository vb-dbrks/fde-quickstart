from fastapi import APIRouter

from app.permissions.deps import CurrentPrincipal
from app.schemas import MeOut

router = APIRouter(tags=["me"])


@router.get("/me")
def me(principal: CurrentPrincipal) -> MeOut:
    """The signed-in user and what they may do. The UI uses this to show or hide actions."""
    return MeOut(
        email=principal.email,
        display_name=principal.display_name,
        roles=sorted(principal.roles),
        permissions=sorted(principal.permissions),
    )
