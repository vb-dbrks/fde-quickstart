from fastapi import APIRouter, status

from backend.api.deps import SessionDep
from backend.auth.access import require_document
from backend.auth.deps import CurrentPrincipal
from backend.domain.schemas import MessageOut, ThreadCreate, ThreadOut
from backend.services import assistant

router = APIRouter(tags=["assistant"])


@router.get("/documents/{document_id}/threads")
async def list_threads(
    document_id: str, principal: CurrentPrincipal, db: SessionDep
) -> list[ThreadOut]:
    """Your conversations about this document (they are private to you)."""
    document, _ = await require_document(db, principal, document_id)
    return [
        ThreadOut.model_validate(t)
        for t in await assistant.list_threads(db, principal, document.id)
    ]


@router.post("/documents/{document_id}/threads", status_code=status.HTTP_201_CREATED)
async def create_thread(
    document_id: str, payload: ThreadCreate, principal: CurrentPrincipal, db: SessionDep
) -> ThreadOut:
    document, _ = await require_document(db, principal, document_id)
    thread = await assistant.create_thread(db, principal, document, title=payload.title)
    await db.commit()
    return ThreadOut.model_validate(thread)


@router.get("/threads/{thread_id}/messages")
async def list_messages(
    thread_id: str, principal: CurrentPrincipal, db: SessionDep
) -> list[MessageOut]:
    thread = await assistant.require_thread(db, principal, thread_id)
    await require_document(db, principal, thread.document_id)
    return [MessageOut.model_validate(m) for m in await assistant.list_messages(db, thread.id)]
