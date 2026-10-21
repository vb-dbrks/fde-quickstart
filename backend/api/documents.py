from fastapi import APIRouter, status
from sqlalchemy import select

from backend.api.deps import CatalogDep, SessionDep
from backend.api.presenters import document_out, document_summary, field_out
from backend.auth.access import require_document
from backend.auth.deps import CurrentPrincipal
from backend.domain.enums import Access, RunStatus
from backend.domain.errors import NotFoundError
from backend.domain.models import AgentRun
from backend.domain.schemas import (
    AccessGrant,
    AccessOut,
    AuditOut,
    DocumentCreate,
    DocumentOut,
    DocumentSummary,
    DocumentTypeOut,
    FieldOut,
    FieldSpecOut,
    FieldUpdate,
    VersionOut,
)
from backend.services import documents

router = APIRouter(tags=["documents"])

_ACTIVE = (RunStatus.QUEUED.value, RunStatus.ACCEPTED.value, RunStatus.RUNNING.value)


@router.get("/document-types")
async def list_document_types(catalog: CatalogDep) -> list[DocumentTypeOut]:
    """The field catalog: document types and their fields."""
    return [
        DocumentTypeOut(
            name=spec.name,
            label=spec.label,
            description=spec.description,
            fields=[
                FieldSpecOut(
                    field_path=f.path,
                    label=f.label,
                    type=f.type,
                    agent_generates=f.agent_generates,
                    required=f.required,
                    description=f.description,
                )
                for f in spec.fields
            ],
        )
        for spec in catalog.document_types.values()
    ]


@router.get("/documents")
async def list_documents(principal: CurrentPrincipal, db: SessionDep) -> list[DocumentSummary]:
    return [
        document_summary(doc, access)
        for doc, access in await documents.list_documents(db, principal)
    ]


async def _document_out(
    db: SessionDep, catalog: CatalogDep, principal: CurrentPrincipal, document_id: str
) -> DocumentOut:
    document, access = await require_document(db, principal, document_id)
    rows = await documents.field_rows(db, document.id)
    active = (
        await db.scalars(
            select(AgentRun)
            .where(AgentRun.document_id == document.id, AgentRun.status.in_(_ACTIVE))
            .where(
                (AgentRun.run_kind != "assistant_turn") | (AgentRun.triggered_by == principal.email)
            )
            .order_by(AgentRun.created_at)
        )
    ).all()
    return document_out(document, access, rows, catalog, active)


@router.post("/documents", status_code=status.HTTP_201_CREATED)
async def create_document(
    payload: DocumentCreate, principal: CurrentPrincipal, db: SessionDep, catalog: CatalogDep
) -> DocumentOut:
    document = await documents.create_document(
        db, catalog, principal, type_name=payload.document_type, values=payload.fields
    )
    await db.commit()
    return await _document_out(db, catalog, principal, document.id)


@router.get("/documents/{document_id}")
async def get_document(
    document_id: str, principal: CurrentPrincipal, db: SessionDep, catalog: CatalogDep
) -> DocumentOut:
    return await _document_out(db, catalog, principal, document_id)


@router.patch("/documents/{document_id}/fields/{field_path}")
async def update_field(
    document_id: str,
    field_path: str,
    payload: FieldUpdate,
    principal: CurrentPrincipal,
    db: SessionDep,
    catalog: CatalogDep,
) -> FieldOut:
    """Edit a field, or accept an enhance_field suggestion (``accepted_from_run_id``)."""
    document, _ = await require_document(db, principal, document_id, Access.EDIT, for_update=True)
    accepted_run = None
    if payload.accepted_from_run_id:
        accepted_run = await db.get(AgentRun, payload.accepted_from_run_id)
        if accepted_run is None or accepted_run.document_id != document.id:
            raise NotFoundError("Run not found")
    row = await documents.update_field(
        db,
        catalog,
        principal,
        document,
        field_path=field_path,
        value=payload.value,
        accepted_run=accepted_run,
    )
    await db.commit()
    return field_out(field_path, catalog, document, row)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: str, principal: CurrentPrincipal, db: SessionDep) -> None:
    document, _ = await require_document(db, principal, document_id, Access.OWNER)
    await documents.delete_document(db, principal, document)
    await db.commit()


@router.get("/documents/{document_id}/versions")
async def list_versions(
    document_id: str, principal: CurrentPrincipal, db: SessionDep
) -> list[VersionOut]:
    document, _ = await require_document(db, principal, document_id)
    return [VersionOut.model_validate(v) for v in await documents.list_versions(db, document.id)]


@router.get("/documents/{document_id}/audit")
async def list_audit(
    document_id: str, principal: CurrentPrincipal, db: SessionDep
) -> list[AuditOut]:
    document, _ = await require_document(db, principal, document_id)
    return [AuditOut.model_validate(a) for a in await documents.list_audit(db, document.id)]


@router.get("/documents/{document_id}/access")
async def list_access(
    document_id: str, principal: CurrentPrincipal, db: SessionDep
) -> list[AccessOut]:
    document, _ = await require_document(db, principal, document_id)
    return [AccessOut.model_validate(a) for a in await documents.list_access(db, document.id)]


@router.put("/documents/{document_id}/access")
async def share_document(
    document_id: str, payload: AccessGrant, principal: CurrentPrincipal, db: SessionDep
) -> AccessOut:
    """Give someone view, edit or owner access (owners only)."""
    document, _ = await require_document(db, principal, document_id, Access.OWNER)
    row = await documents.share(db, principal, document, email=payload.email, access=payload.access)
    await db.commit()
    return AccessOut.model_validate(row)


@router.delete("/documents/{document_id}/access/{email}", status_code=status.HTTP_204_NO_CONTENT)
async def unshare_document(
    document_id: str, email: str, principal: CurrentPrincipal, db: SessionDep
) -> None:
    document, _ = await require_document(db, principal, document_id, Access.OWNER)
    await documents.unshare(db, principal, document, email=email)
    await db.commit()
