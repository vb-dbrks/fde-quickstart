"""FastAPI dependencies for authentication and authorization."""

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from backend.api.deps import SessionDep, SettingsDep
from backend.auth.identity import identity_from_request
from backend.auth.principal import Principal, resolve_principal
from backend.auth.roles import Permission


async def get_principal(request: Request, db: SessionDep, settings: SettingsDep) -> Principal:
    return await resolve_principal(db, identity_from_request(request, settings), settings)


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


def require(permission: Permission) -> Callable[[Principal], Awaitable[Principal]]:
    """Dependency returning the current principal, or failing with 403 without ``permission``.

    Usage::

        Creator = Annotated[Principal, Depends(require(Permission.DOCUMENTS_CREATE))]
    """

    async def dependency(principal: CurrentPrincipal) -> Principal:
        if not principal.can(permission):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing permission: {permission}")
        return principal

    return dependency
