"""Per-document access: owner, edit or view. Users with documents:access_any are owners of all.

No access at all answers 404 (we don't reveal that a document exists); too little answers 403.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.principal import Principal
from backend.auth.roles import Permission
from backend.domain.enums import Access
from backend.domain.errors import ForbiddenError, NotFoundError
from backend.domain.models import Document, DocumentAccess


async def access_level(db: AsyncSession, principal: Principal, document_id: str) -> Access | None:
    if principal.can(Permission.DOCUMENTS_ACCESS_ANY):
        return Access.OWNER
    level = await db.scalar(
        select(DocumentAccess.access).where(
            DocumentAccess.document_id == document_id,
            DocumentAccess.principal == principal.email,
        )
    )
    return Access(level) if level else None


async def require_document(
    db: AsyncSession,
    principal: Principal,
    document_id: str,
    minimum: Access = Access.VIEW,
    *,
    for_update: bool = False,
) -> tuple[Document, Access]:
    query = select(Document).where(Document.id == document_id, Document.deleted_at.is_(None))
    if for_update:
        query = query.with_for_update()
    document = await db.scalar(query)
    level = await access_level(db, principal, document_id) if document else None
    if document is None or level is None:
        raise NotFoundError("Document not found")
    if not level.allows(minimum):
        raise ForbiddenError(f"This needs {minimum} access to the document")
    return document, level
