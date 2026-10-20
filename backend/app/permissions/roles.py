"""Roles and permissions.

Code checks permissions (``require(Permission.NOTES_WRITE)``). Roles are named sets of permissions that
admins assign to users. Add new permissions and roles here; assignments are stored in the
``role_assignments`` table.
"""

from collections.abc import Iterable, Mapping
from enum import StrEnum
from types import MappingProxyType


class Permission(StrEnum):
    NOTES_READ = "notes:read"
    NOTES_WRITE = "notes:write"
    NOTES_DELETE_ANY = "notes:delete_any"
    AGENTS_INVOKE = "agents:invoke"
    ROLES_MANAGE = "roles:manage"


class Role(StrEnum):
    VIEWER = "viewer"
    EDITOR = "editor"
    ADMIN = "admin"


_VIEWER = frozenset({Permission.NOTES_READ})
_EDITOR = _VIEWER | {Permission.NOTES_WRITE, Permission.AGENTS_INVOKE}

ROLE_PERMISSIONS: Mapping[Role, frozenset[Permission]] = MappingProxyType(
    {
        Role.VIEWER: _VIEWER,
        Role.EDITOR: _EDITOR,
        Role.ADMIN: frozenset(Permission),
    }
)


def permissions_for(roles: Iterable[Role]) -> frozenset[Permission]:
    granted: set[Permission] = set()
    for role in roles:
        granted |= ROLE_PERMISSIONS[role]
    return frozenset(granted)
