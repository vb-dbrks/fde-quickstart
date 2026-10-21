from fastapi import APIRouter

from backend.auth.deps import CurrentPrincipal
from backend.domain.schemas import MeOut

router = APIRouter(tags=["me"])


@router.get("/me")
async def me(principal: CurrentPrincipal) -> MeOut:
    """The signed-in user and their app-wide permissions. The UI uses this to show or hide actions."""
    return MeOut(
        email=principal.email,
        display_name=principal.display_name,
        roles=sorted(principal.roles),
        permissions=sorted(principal.permissions),
    )
