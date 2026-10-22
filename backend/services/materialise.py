"""Write a succeeded ``generate`` run's output to its document, atomically.

Runs inside the caller's transaction (no commit here), with the agent_runs row locked by the caller:

  1. Re-check the output against the request and the field catalog (defence in depth).
  2. Upsert each field with its provenance (confidence, reasoning, citations, run id).
  3. Snapshot every field as a new ``document_versions`` row.
  4. Append one ``audit_log`` row per field (generate, or regenerate if it had a value).
  5. Stamp ``agent_runs.materialised_at`` so a second poll is a no-op.
"""

from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

from backend.contracts.agent_contract_v1 import AgentOutput, AgentRunRequest
from backend.contracts.field_catalog import FieldCatalog
from backend.contracts.validation import check_output
from backend.domain.enums import AuditAction, FieldSource
from backend.domain.models import AgentRun, Document, DocumentField, DocumentVersion
from backend.services.documents import audit, field_rows, field_values


class MaterialisationError(Exception):
    code = "MATERIALISATION_FAILED"


async def materialise_generate(
    db: AsyncSession,
    *,
    run: AgentRun,
    document: Document,
    output: AgentOutput,
    catalog: FieldCatalog,
    trace_id: str | None,
) -> None:
    if run.materialised_at is not None:
        return
    request = AgentRunRequest.model_validate(run.request_payload)
    problems = check_output(request, output, catalog)
    if problems:
        raise MaterialisationError("; ".join(problems))
    doc_type = catalog.get(document.document_type)
    if doc_type is None:
        raise MaterialisationError(f"unknown document type {document.document_type!r}")

    rows = await field_rows(db, document.id)
    actor = run.triggered_by
    for field in output.fields:
        spec = doc_type.field(field.field_path)
        if spec is None:  # pragma: no cover - check_output already rejects this
            continue
        value = spec.coerce(field.value)
        citations = [citation.model_dump(mode="json") for citation in field.citations]
        row = rows.get(field.field_path)
        before = row.value if row else None
        if row is None:
            row = DocumentField(document_id=document.id, field_path=field.field_path)
            db.add(row)
            rows[field.field_path] = row
        row.revision = (row.revision or 0) + 1
        row.value = value
        row.source = FieldSource.AGENT.value
        row.confidence = field.confidence
        row.confidence_reason = field.confidence_reason
        row.reasoning = field.reasoning
        row.citations = citations
        row.agent_run_id = run.id
        row.updated_by = actor
        action = AuditAction.REGENERATE if before not in (None, "", []) else AuditAction.GENERATE
        db.add(
            audit(
                document.id,
                action,
                actor,
                field_path=field.field_path,
                before=before,
                after=value,
                agent_run_id=run.id,
                trace_id=trace_id,
            )
        )

    # In SQL, not Python: two runs materialising into the same document at once must each get their
    # own version number, whatever their copy of the document says.
    now = datetime.now(UTC)
    version = await db.scalar(
        update(Document)
        .where(Document.id == document.id)
        .values(current_version=Document.current_version + 1, updated_at=now)
        .returning(Document.current_version)
        .execution_options(synchronize_session=False)
    )
    set_committed_value(document, "current_version", version)
    set_committed_value(document, "updated_at", now)
    db.add(
        DocumentVersion(
            document_id=document.id,
            version=version,
            snapshot=field_values(rows),
            agent_run_id=run.id,
            created_by=actor,
        )
    )
    run.materialised_at = datetime.now(UTC)
