"""Document-owned review transactions. Generic execution never writes document fields."""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import CatalogDep, DeliverFeedback, SessionDep
from backend.auth.access import require_document
from backend.auth.deps import CurrentPrincipal
from backend.auth.principal import Principal
from backend.contracts.agent_contract_v1 import AgentOutput
from backend.contracts.field_catalog import FieldCatalog
from backend.domain.enums import Access
from backend.domain.errors import ConflictError, InvalidInputError, NotFoundError
from backend.domain.models import AgentRun, Document, DocumentVersion, FieldProposal
from backend.services import documents, feedback

router = APIRouter(tags=["document proposals"])


async def create_proposals(db: AsyncSession, run: AgentRun, output: AgentOutput) -> None:
    from backend.contracts.agent_contract_v1 import AgentRunRequest
    from backend.contracts.field_catalog import load_field_catalog
    from backend.contracts.validation import check_output

    problems = check_output(
        AgentRunRequest.model_validate(run.request_payload), output, load_field_catalog()
    )
    if problems:
        from backend.services.materialise import MaterialisationError

        raise MaterialisationError("; ".join(problems))
    captured = run.request_payload.get("_field_revisions", {})
    fields = run.request_payload["document_context"]["fields"]
    for item in output.fields:
        db.add(
            FieldProposal(
                run_id=run.id,
                document_id=run.document_id,
                field_path=item.field_path,
                base_revision=captured.get(item.field_path, 0),
                before=fields.get(item.field_path),
                output=item.model_dump(mode="json"),
                status="pending",
            )
        )
    run.materialised_at = datetime.now(UTC)


class ProposalOut(BaseModel):
    run_id: str
    field_path: str
    before: Any = None
    output: dict[str, Any]
    status: str


class ProposalReview(BaseModel):
    accept: dict[str, Any] = Field(default_factory=dict)
    reject: list[str] = Field(default_factory=list)


@router.get("/documents/{document_id}/proposals")
async def proposals(
    document_id: str, db: SessionDep, principal: CurrentPrincipal
) -> list[ProposalOut]:
    await require_document(db, principal, document_id)
    rows = await db.scalars(
        select(FieldProposal)
        .where(FieldProposal.document_id == document_id, FieldProposal.status == "pending")
        .order_by(FieldProposal.run_id, FieldProposal.field_path)
    )
    return [
        ProposalOut(
            run_id=p.run_id,
            field_path=p.field_path,
            before=p.before,
            output=p.output,
            status=p.status,
        )
        for p in rows
    ]


async def apply_review(
    db: AsyncSession,
    principal: Principal,
    document: Document,
    run: AgentRun,
    catalog: FieldCatalog,
    payload: ProposalReview,
) -> None:
    selected = set(payload.accept) | set(payload.reject)
    if not selected or set(payload.accept) & set(payload.reject):
        raise InvalidInputError("Select fields to accept or reject, without overlap")
    rows = {
        p.field_path: p
        for p in await db.scalars(
            select(FieldProposal).where(FieldProposal.run_id == run.id).with_for_update()
        )
    }
    if not selected <= rows.keys():
        raise NotFoundError("Proposal not found")
    current = await documents.field_rows(db, document.id)
    for path in selected:
        proposal = rows[path]
        decision = "accepted" if path in payload.accept else "rejected"
        if proposal.status != "pending":
            if proposal.status != decision or (
                decision == "accepted" and proposal.accepted_value != payload.accept[path]
            ):
                raise ConflictError("This proposal has already been reviewed")
            continue
        if path in payload.accept:
            revision = current[path].revision if path in current else 0
            if revision != proposal.base_revision:
                raise ConflictError(
                    f"{path} changed since this draft. Review the latest value and regenerate."
                )
    changed = False
    for path in selected:
        proposal = rows[path]
        if proposal.status != "pending":
            continue
        if path in payload.accept:
            value = payload.accept[path]
            await documents.update_field(
                db, catalog, principal, document, field_path=path, value=value, accepted_run=run
            )
            proposal.accepted_value = value
            proposal.status = "accepted"
            if value != proposal.output["value"]:
                await feedback.record_correction(db, principal, run, path, value)
            changed = True
        else:
            proposal.status = "rejected"
            await feedback.record_verdict(db, principal, run, path, accepted=False)
    if changed:
        document.current_version += 1
        await db.flush()
        snapshot = documents.field_values(await documents.field_rows(db, document.id))
        db.add(
            DocumentVersion(
                document_id=document.id,
                version=document.current_version,
                snapshot=snapshot,
                agent_run_id=run.id,
                created_by=principal.email,
            )
        )


@router.post("/documents/{document_id}/proposals/{run_id}/review")
async def review_proposals(
    document_id: str,
    run_id: str,
    payload: ProposalReview,
    db: SessionDep,
    principal: CurrentPrincipal,
    catalog: CatalogDep,
    deliver: DeliverFeedback,
) -> dict[str, bool]:
    document, _ = await require_document(db, principal, document_id, Access.EDIT, for_update=True)
    run = await db.get(AgentRun, run_id)
    if run is None or run.document_id != document_id or run.status != "succeeded":
        raise NotFoundError("Completed run not found")
    await apply_review(db, principal, document, run, catalog, payload)
    await db.commit()
    deliver()
    return {"reviewed": True}
