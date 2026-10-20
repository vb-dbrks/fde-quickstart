from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app import notes
from app.deps import SessionDep
from app.models import Note
from app.permissions.deps import CurrentPrincipal, require
from app.permissions.roles import Permission
from app.permissions.service import Principal
from app.schemas import NoteIn, NoteOut

router = APIRouter(prefix="/notes", tags=["notes"])

Reader = Annotated[Principal, Depends(require(Permission.NOTES_READ))]
Writer = Annotated[Principal, Depends(require(Permission.NOTES_WRITE))]


def _to_out(note: Note, principal: Principal) -> NoteOut:
    return NoteOut(
        id=note.id,
        title=note.title,
        body=note.body,
        owner=note.owner,
        created_at=note.created_at,
        can_delete=notes.can_delete(principal, note),
    )


@router.get("")
def list_notes(principal: Reader, session: SessionDep, mine: bool = False) -> list[NoteOut]:
    found = notes.list_notes(session, owner=principal.email if mine else None)
    return [_to_out(note, principal) for note in found]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_note(payload: NoteIn, principal: Writer, session: SessionDep) -> NoteOut:
    note = notes.create_note(session, owner=principal.email, title=payload.title, body=payload.body)
    session.commit()
    return _to_out(note, principal)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(note_id: int, principal: CurrentPrincipal, session: SessionDep) -> None:
    note = session.get(Note, note_id)
    if note is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Note not found")
    if not notes.can_delete(principal, note):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only delete your own notes")
    session.delete(note)
    session.commit()
