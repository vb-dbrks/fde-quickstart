from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.deps import NotifierDep, SessionDep
from app.models import RoleAssignment
from app.permissions import service
from app.permissions.deps import require
from app.permissions.roles import ROLE_PERMISSIONS, Permission, Role
from app.permissions.service import Principal
from app.schemas import RoleAssignmentOut, RoleGrantIn, RoleInfo

router = APIRouter(prefix="/admin", tags=["admin"])

Admin = Annotated[Principal, Depends(require(Permission.ROLES_MANAGE))]


@router.get("/roles")
def list_roles(_: Admin) -> list[RoleInfo]:
    """The roles defined in code and the permissions each grants."""
    return [RoleInfo(role=role, permissions=sorted(ROLE_PERMISSIONS[role])) for role in Role]


@router.get("/role-assignments")
def list_role_assignments(_: Admin, session: SessionDep) -> list[RoleAssignmentOut]:
    return [RoleAssignmentOut.model_validate(a) for a in service.list_assignments(session)]


@router.post(
    "/role-assignments",
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_200_OK: {"description": "The user already had this role"}},
)
def grant_role(
    payload: RoleGrantIn,
    admin: Admin,
    session: SessionDep,
    notifier: NotifierDep,
    response: Response,
) -> RoleAssignmentOut:
    created = service.grant_role(
        session, notifier, email=payload.email, role=payload.role, granted_by=admin.email
    )
    session.commit()
    if not created:
        response.status_code = status.HTTP_200_OK
    assignment = session.get(RoleAssignment, (payload.email.strip().lower(), payload.role.value))
    return RoleAssignmentOut.model_validate(assignment)


@router.delete("/role-assignments/{email}/{role}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_role(email: str, role: Role, _: Admin, session: SessionDep) -> None:
    if not service.revoke_role(session, email=email, role=role):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role assignment not found")
    session.commit()
