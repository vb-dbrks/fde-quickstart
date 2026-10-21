"""Resolving a user's roles, and granting or revoking them."""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.identity import Identity
from backend.auth.roles import Permission, Role, permissions_for
from backend.domain.models import RoleAssignment
from backend.services.notification_channels import Message
from backend.services.notifications import Notifier
from backend.settings import Settings

_ROLE_VALUES = frozenset(role.value for role in Role)


@dataclass(frozen=True)
class Principal:
    """A signed-in user with their effective roles and permissions."""

    email: str
    display_name: str
    roles: frozenset[Role]
    permissions: frozenset[Permission]

    def can(self, permission: Permission) -> bool:
        return permission in self.permissions


async def resolve_principal(db: AsyncSession, identity: Identity, settings: Settings) -> Principal:
    assigned = await db.scalars(
        select(RoleAssignment.role).where(RoleAssignment.principal == identity.email)
    )
    # Ignore stored roles that no longer exist in code.
    roles = {Role(value) for value in assigned if value in _ROLE_VALUES}
    roles.add(settings.app_default_role)
    if identity.email in settings.admin_emails:
        roles.add(Role.ADMIN)
    return Principal(
        email=identity.email,
        display_name=identity.display_name,
        roles=frozenset(roles),
        permissions=permissions_for(roles),
    )


async def list_assignments(db: AsyncSession) -> Sequence[RoleAssignment]:
    query = select(RoleAssignment).order_by(RoleAssignment.principal, RoleAssignment.role)
    return (await db.scalars(query)).all()


async def grant_role(
    db: AsyncSession, notifier: Notifier, *, email: str, role: Role, granted_by: str
) -> bool:
    """Grant ``role`` to ``email`` and notify them. Returns False if they already had it."""
    email = email.strip().lower()
    inserted = (
        await db.execute(
            insert(RoleAssignment)
            .values(principal=email, role=role.value, granted_by=granted_by)
            .on_conflict_do_nothing()
            .returning(RoleAssignment.principal)
        )
    ).first()
    if inserted is None:
        return False
    await notifier.notify(
        db,
        Message(
            recipient=email,
            kind="role_granted",
            title=f"You now have the {role} role",
            body=f"Granted by {granted_by}.",
            link="/",
        ),
    )
    return True


async def revoke_role(db: AsyncSession, *, email: str, role: Role) -> bool:
    deleted = (
        await db.execute(
            delete(RoleAssignment)
            .where(
                RoleAssignment.principal == email.strip().lower(), RoleAssignment.role == role.value
            )
            .returning(RoleAssignment.principal)
        )
    ).first()
    return deleted is not None
