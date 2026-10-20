"""Tools the agents can call.

Each tool acts as the calling user (``AgentContext.principal``) and checks the same permissions as the
REST API, so an agent can never do more than the user could themselves. The logic lives in plain
functions that are easy to test; the ``@function_tool`` wrappers expose them to the OpenAI Agents SDK.
"""

import asyncio
import json

from agents import RunContextWrapper, Tool, function_tool

from app import notes
from app.agents.base import AgentContext
from app.permissions.roles import Permission

PERMISSION_DENIED = "Permission denied: the user is not allowed to do this."
MAX_NOTES = 20


def describe_user(context: AgentContext) -> dict[str, object]:
    principal = context.principal
    return {
        "email": principal.email,
        "name": principal.display_name,
        "roles": sorted(principal.roles),
        "permissions": sorted(principal.permissions),
    }


def recent_notes(
    context: AgentContext, *, limit: int = 5, mine_only: bool = False
) -> list[dict[str, object]] | str:
    principal = context.principal
    if not principal.can(Permission.NOTES_READ):
        return PERMISSION_DENIED
    with context.sessions() as session:
        found = notes.list_notes(
            session,
            owner=principal.email if mine_only else None,
            limit=max(1, min(limit, MAX_NOTES)),
        )
        return [
            {
                "id": note.id,
                "title": note.title,
                "body": note.body[:1000],
                "owner": note.owner,
                "created_at": note.created_at.isoformat(),
            }
            for note in found
        ]


def add_note(context: AgentContext, *, title: str, body: str) -> dict[str, object] | str:
    principal = context.principal
    if not principal.can(Permission.NOTES_WRITE):
        return PERMISSION_DENIED
    with context.sessions() as session:
        note = notes.create_note(session, owner=principal.email, title=title[:200], body=body)
        session.commit()
        return {"id": note.id, "title": note.title}


@function_tool
def whoami(wrapper: RunContextWrapper[AgentContext]) -> str:
    """Return the current user's email, name, roles and permissions."""
    return json.dumps(describe_user(wrapper.context))


@function_tool
async def list_recent_notes(
    wrapper: RunContextWrapper[AgentContext], limit: int = 5, mine_only: bool = False
) -> str:
    """List the most recent notes the user can see, newest first.

    Args:
        limit: How many notes to return (1-20).
        mine_only: Only include notes the user wrote.
    """
    found = await asyncio.to_thread(recent_notes, wrapper.context, limit=limit, mine_only=mine_only)
    return json.dumps(found)


@function_tool
async def create_note(wrapper: RunContextWrapper[AgentContext], title: str, body: str) -> str:
    """Create a note owned by the user. Only use this when the user asks for a note.

    Args:
        title: Short title, at most 200 characters.
        body: The note text.
    """
    created = await asyncio.to_thread(add_note, wrapper.context, title=title, body=body)
    return json.dumps(created)


TOOLS: tuple[Tool, ...] = (whoami, list_recent_notes, create_note)
