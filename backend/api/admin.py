from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from backend.api.deps import NotifierDep, SessionDep
from backend.auth import principal as principals
from backend.auth.deps import require
from backend.auth.principal import Principal
from backend.auth.roles import ROLE_PERMISSIONS, Permission, Role
from backend.domain.models import RoleAssignment
from backend.domain.schemas import RoleAssignmentOut, RoleGrantIn, RoleInfo

router = APIRouter(prefix="/admin", tags=["admin"])

Admin = Annotated[Principal, Depends(require(Permission.ROLES_MANAGE))]


@router.get("/roles")
async def list_roles(_: Admin) -> list[RoleInfo]:
    """The roles defined in code and the permissions each grants."""
    return [RoleInfo(role=role, permissions=sorted(ROLE_PERMISSIONS[role])) for role in Role]


@router.get("/role-assignments")
async def list_role_assignments(_: Admin, db: SessionDep) -> list[RoleAssignmentOut]:
    return [RoleAssignmentOut.model_validate(a) for a in await principals.list_assignments(db)]


@router.post(
    "/role-assignments",
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_200_OK: {"description": "The user already had this role"}},
)
async def grant_role(
    payload: RoleGrantIn, admin: Admin, db: SessionDep, notifier: NotifierDep, response: Response
) -> RoleAssignmentOut:
    created = await principals.grant_role(
        db, notifier, email=payload.email, role=payload.role, granted_by=admin.email
    )
    await db.commit()
    if not created:
        response.status_code = status.HTTP_200_OK
    assignment = await db.get(RoleAssignment, (payload.email.strip().lower(), payload.role.value))
    return RoleAssignmentOut.model_validate(assignment)


@router.delete("/role-assignments/{email}/{role}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_role(email: str, role: Role, _: Admin, db: SessionDep) -> None:
    if not await principals.revoke_role(db, email=email, role=role):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role assignment not found")
    await db.commit()
