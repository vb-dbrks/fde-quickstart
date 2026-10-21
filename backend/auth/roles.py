"""App-wide roles and permissions.

Code checks permissions (``require(Permission.DOCUMENTS_CREATE)``). Roles are named sets of
permissions that admins assign to users; assignments are stored in ``role_assignments``. Which
documents a user can see or change is decided separately, per document (backend.auth.access).
"""

from collections.abc import Iterable, Mapping
from enum import StrEnum
from types import MappingProxyType


class Permission(StrEnum):
    DOCUMENTS_CREATE = "documents:create"
    AGENTS_RUN = "agents:run"
    # See and manage every document, regardless of per-document access.
    DOCUMENTS_ACCESS_ANY = "documents:access_any"
    ROLES_MANAGE = "roles:manage"


class Role(StrEnum):
    VIEWER = "viewer"
    EDITOR = "editor"
    ADMIN = "admin"


ROLE_PERMISSIONS: Mapping[Role, frozenset[Permission]] = MappingProxyType(
    {
        # Viewers only see documents shared with them.
        Role.VIEWER: frozenset(),
        Role.EDITOR: frozenset({Permission.DOCUMENTS_CREATE, Permission.AGENTS_RUN}),
        Role.ADMIN: frozenset(Permission),
    }
)


def permissions_for(roles: Iterable[Role]) -> frozenset[Permission]:
    granted: set[Permission] = set()
    for role in roles:
        granted |= ROLE_PERMISSIONS[role]
    return frozenset(granted)
