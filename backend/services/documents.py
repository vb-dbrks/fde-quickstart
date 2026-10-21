"""Documents: create, read, edit and share. Content is one row per field from the field catalog."""

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.principal import Principal
from backend.auth.roles import Permission
from backend.contracts.agent_contract_v1 import AgentRunStatus
from backend.contracts.field_catalog import DocumentTypeSpec, FieldCatalog
from backend.domain.enums import Access, AuditAction, FieldSource, RunStatus
from backend.domain.errors import ConflictError, ForbiddenError, InvalidInputError, NotFoundError
from backend.domain.models import (
    AgentRun,
    AuditLog,
    Document,
    DocumentAccess,
    DocumentField,
    DocumentVersion,
)
from backend.services import feedback


def document_type(catalog: FieldCatalog, name: str) -> DocumentTypeSpec:
    spec = catalog.get(name)
    if spec is None:
        raise InvalidInputError(f"Unknown document type {name!r}")
    return spec


async def field_rows(db: AsyncSession, document_id: str) -> dict[str, DocumentField]:
    rows = await db.scalars(select(DocumentField).where(DocumentField.document_id == document_id))
    return {row.field_path: row for row in rows}


def field_values(rows: Mapping[str, DocumentField]) -> dict[str, Any]:
    return {path: row.value for path, row in rows.items() if row.value is not None}


def audit(
    document_id: str,
    action: AuditAction,
    actor: str,
    *,
    field_path: str | None = None,
    before: Any = None,
    after: Any = None,
    agent_run_id: str | None = None,
    trace_id: str | None = None,
) -> AuditLog:
    return AuditLog(
        document_id=document_id,
        field_path=field_path,
        action=action.value,
        value_before=before,
        value_after=after,
        actor=actor,
        agent_run_id=agent_run_id,
        trace_id=trace_id,
    )


async def create_document(
    db: AsyncSession,
    catalog: FieldCatalog,
    principal: Principal,
    *,
    type_name: str,
    values: Mapping[str, Any],
) -> Document:
    if not principal.can(Permission.DOCUMENTS_CREATE):
        raise ForbiddenError(f"Missing permission: {Permission.DOCUMENTS_CREATE}")
    spec = document_type(catalog, type_name)
    clean: dict[str, Any] = {}
    for path, value in values.items():
        field = spec.field(path)
        if field is None:
            raise InvalidInputError(f"Unknown field {path!r} for {type_name}")
        try:
            clean[path] = field.coerce(value)
        except ValueError as exc:
            raise InvalidInputError(str(exc)) from exc
    missing = [f.label for f in spec.fields if f.required and not clean.get(f.path)]
    if missing:
        raise InvalidInputError(f"Required: {', '.join(missing)}")

    document = Document(
        document_type=type_name,
        title=str(clean[spec.title_field])[:200],
        created_by=principal.email,
    )
    db.add(document)
    await db.flush()
    db.add(
        DocumentAccess(
            document_id=document.id,
            principal=principal.email,
            access=Access.OWNER.value,
            granted_by=principal.email,
        )
    )
    for path, value in clean.items():
        if value in (None, "", []):
            continue
        db.add(
            DocumentField(
                document_id=document.id,
                field_path=path,
                value=value,
                source=FieldSource.USER.value,
                citations=[],
                updated_by=principal.email,
            )
        )
        db.add(
            audit(document.id, AuditAction.CREATE, principal.email, field_path=path, after=value)
        )
    return document


async def list_documents(db: AsyncSession, principal: Principal) -> list[tuple[Document, Access]]:
    if principal.can(Permission.DOCUMENTS_ACCESS_ANY):
        docs = await db.scalars(
            select(Document)
            .where(Document.deleted_at.is_(None))
            .order_by(Document.updated_at.desc())
        )
        return [(doc, Access.OWNER) for doc in docs]
    rows = await db.execute(
        select(Document, DocumentAccess.access)
        .join(DocumentAccess, DocumentAccess.document_id == Document.id)
        .where(DocumentAccess.principal == principal.email, Document.deleted_at.is_(None))
        .order_by(Document.updated_at.desc())
    )
    return [(doc, Access(level)) for doc, level in rows]


async def accessible_documents(
    db: AsyncSession, principal: Principal, document_ids: Sequence[str]
) -> list[Document]:
    """The documents in ``document_ids`` the principal can see (others are silently dropped)."""
    if not document_ids:
        return []
    query = select(Document).where(Document.id.in_(document_ids), Document.deleted_at.is_(None))
    if not principal.can(Permission.DOCUMENTS_ACCESS_ANY):
        query = query.join(DocumentAccess, DocumentAccess.document_id == Document.id).where(
            DocumentAccess.principal == principal.email
        )
    return list((await db.scalars(query)).all())


async def update_field(
    db: AsyncSession,
    catalog: FieldCatalog,
    principal: Principal,
    document: Document,
    *,
    field_path: str,
    value: Any,
    accepted_run: AgentRun | None = None,
) -> DocumentField:
    """Write a field. With ``accepted_run``, the user accepts an enhance_field suggestion."""
    spec = document_type(catalog, document.document_type).field(field_path)
    if spec is None:
        raise NotFoundError(f"Unknown field {field_path!r}")
    try:
        clean = spec.coerce(value)
    except ValueError as exc:
        raise InvalidInputError(str(exc)) from exc
    if field_path == f"{document.document_type}.title" and not clean:
        raise InvalidInputError("The title can't be empty")

    provenance: dict[str, Any] = {
        "source": FieldSource.USER.value,
        "confidence": None,
        "confidence_reason": None,
        "reasoning": None,
        "citations": [],
        "agent_run_id": None,
    }
    action = AuditAction.UPDATE
    trace_id = None
    if accepted_run is not None:
        suggestion = suggestion_for(accepted_run, field_path)
        if suggestion is None:
            raise ConflictError("That run has no suggestion for this field")
        provenance.update(
            source=FieldSource.AGENT.value,
            confidence=suggestion.get("confidence"),
            confidence_reason=suggestion.get("confidence_reason"),
            reasoning=suggestion.get("reasoning"),
            citations=suggestion.get("citations") or [],
            agent_run_id=accepted_run.id,
        )
        action = AuditAction.ACCEPT_SUGGESTION
        trace_id = accepted_run.mlflow_trace_id

    existing = (await field_rows(db, document.id)).get(field_path)
    before = existing.value if existing else None
    # Feedback on the agent (services/feedback.py): accepting a suggestion is a verdict; changing a
    # value the agent wrote makes the new value the expected one for the run that wrote it.
    if accepted_run is not None:
        await feedback.record_verdict(db, principal, accepted_run, field_path, accepted=True)
    elif (
        existing is not None
        and existing.source == FieldSource.AGENT
        and existing.agent_run_id
        and clean != existing.value
        and (written_by := await db.get(AgentRun, existing.agent_run_id)) is not None
    ):
        await feedback.record_correction(db, principal, written_by, field_path, clean)
    values = {"value": clean, "updated_by": principal.email, **provenance}
    statement = insert(DocumentField).values(
        document_id=document.id, field_path=field_path, **values
    )
    await db.execute(
        statement.on_conflict_do_update(
            index_elements=[DocumentField.document_id, DocumentField.field_path],
            set_={**values, "updated_at": datetime.now(UTC)},
        )
    )
    if field_path == f"{document.document_type}.title":
        document.title = str(clean)[:200]
    document.updated_at = datetime.now(UTC)
    db.add(
        audit(
            document.id,
            action,
            principal.email,
            field_path=field_path,
            before=before,
            after=clean,
            agent_run_id=accepted_run.id if accepted_run else None,
            trace_id=trace_id,
        )
    )
    await db.flush()
    row = (await field_rows(db, document.id))[field_path]
    await db.refresh(row)
    return row


def suggestion_for(run: AgentRun, field_path: str) -> dict[str, Any] | None:
    """The suggested field from a succeeded enhance_field run, as stored in ``response_payload``."""
    if (
        run.run_kind != "enhance_field"
        or run.status != RunStatus.SUCCEEDED
        or not run.response_payload
    ):
        return None
    status = AgentRunStatus.model_validate(run.response_payload)
    for field in status.output.fields if status.output else []:
        if field.field_path == field_path:
            return field.model_dump(mode="json")
    return None


async def delete_document(db: AsyncSession, principal: Principal, document: Document) -> None:
    document.deleted_at = datetime.now(UTC)
    db.add(audit(document.id, AuditAction.DELETE, principal.email))


async def list_versions(db: AsyncSession, document_id: str) -> Sequence[DocumentVersion]:
    query = (
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.version.desc())
    )
    return (await db.scalars(query)).all()


async def list_audit(db: AsyncSession, document_id: str, *, limit: int = 100) -> Sequence[AuditLog]:
    query = (
        select(AuditLog)
        .where(AuditLog.document_id == document_id)
        .order_by(AuditLog.id.desc())
        .limit(limit)
    )
    return (await db.scalars(query)).all()


async def list_access(db: AsyncSession, document_id: str) -> Sequence[DocumentAccess]:
    query = (
        select(DocumentAccess)
        .where(DocumentAccess.document_id == document_id)
        .order_by(DocumentAccess.granted_at)
    )
    return (await db.scalars(query)).all()


async def share(
    db: AsyncSession, principal: Principal, document: Document, *, email: str, access: Access
) -> DocumentAccess:
    email = email.strip().lower()
    if email == principal.email and access != Access.OWNER:
        raise InvalidInputError("You can't lower your own access")
    if access != Access.OWNER:
        owners = [row for row in await list_access(db, document.id) if row.access == Access.OWNER]
        if [row.principal for row in owners] == [email]:
            raise ConflictError("A document needs at least one owner")
    values = {"access": access.value, "granted_by": principal.email}
    await db.execute(
        insert(DocumentAccess)
        .values(document_id=document.id, principal=email, **values)
        .on_conflict_do_update(
            index_elements=[DocumentAccess.document_id, DocumentAccess.principal], set_=values
        )
    )
    db.add(
        audit(
            document.id,
            AuditAction.SHARE,
            principal.email,
            after={"principal": email, "access": access.value},
        )
    )
    row = await db.scalar(
        select(DocumentAccess).where(
            DocumentAccess.document_id == document.id, DocumentAccess.principal == email
        )
    )
    assert row is not None
    await db.refresh(row)
    return row


async def unshare(
    db: AsyncSession, principal: Principal, document: Document, *, email: str
) -> None:
    email = email.strip().lower()
    owners = [row for row in await list_access(db, document.id) if row.access == Access.OWNER]
    if len(owners) == 1 and owners[0].principal == email:
        raise ConflictError("A document needs at least one owner")
    deleted = (
        await db.execute(
            delete(DocumentAccess)
            .where(DocumentAccess.document_id == document.id, DocumentAccess.principal == email)
            .returning(DocumentAccess.principal)
        )
    ).first()
    if deleted is None:
        raise NotFoundError("That person has no access")
    db.add(audit(document.id, AuditAction.UNSHARE, principal.email, before={"principal": email}))
