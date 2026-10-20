"""FastAPI dependencies for authentication and authorization."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.deps import SessionDep, SettingsDep
from app.identity import identity_from_request
from app.permissions.roles import Permission
from app.permissions.service import Principal, resolve_principal


def get_principal(request: Request, session: SessionDep, settings: SettingsDep) -> Principal:
    return resolve_principal(session, identity_from_request(request, settings), settings)


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


def require(permission: Permission) -> Callable[[Principal], Principal]:
    """Dependency returning the current principal, or failing with 403 without ``permission``.

    Usage::

        Writer = Annotated[Principal, Depends(require(Permission.NOTES_WRITE))]

        @router.post("/notes")
        def create_note(principal: Writer) -> NoteOut: ...
    """

    def dependency(principal: CurrentPrincipal) -> Principal:
        if not principal.can(permission):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing permission: {permission}")
        return principal

    return dependency
