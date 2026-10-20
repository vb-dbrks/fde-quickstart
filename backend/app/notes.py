"""Notes: the sample feature that exercises the Lakebase round trip. Replace it with your own domain."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Note
from app.permissions.roles import Permission
from app.permissions.service import Principal


def list_notes(session: Session, *, owner: str | None = None, limit: int = 100) -> Sequence[Note]:
    query = select(Note)
    if owner is not None:
        query = query.where(Note.owner == owner)
    return session.scalars(query.order_by(Note.id.desc()).limit(limit)).all()


def create_note(session: Session, *, owner: str, title: str, body: str = "") -> Note:
    note = Note(owner=owner, title=title, body=body)
    session.add(note)
    session.flush()
    return note


def can_delete(principal: Principal, note: Note) -> bool:
    if principal.can(Permission.NOTES_DELETE_ANY):
        return True
    return note.owner == principal.email and principal.can(Permission.NOTES_WRITE)
