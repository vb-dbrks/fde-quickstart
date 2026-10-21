"""Convert ORM rows to API schemas."""

from collections.abc import Mapping, Sequence

from backend.contracts.agent_contract_v1 import AgentRunStatus
from backend.contracts.field_catalog import FieldCatalog
from backend.domain.enums import Access, FieldSource, RunStatus
from backend.domain.models import AgentRun, Document, DocumentField, Feedback
from backend.domain.schemas import (
    AgentRunOut,
    CitationOut,
    DocumentOut,
    DocumentSummary,
    FieldOut,
    RatingOut,
    StepOut,
    SuggestionOut,
)

# The principal's ratings, keyed by (agent run id, field path or message:<id>).
Ratings = Mapping[tuple[str, str], Feedback]


def document_summary(document: Document, access: Access) -> DocumentSummary:
    return DocumentSummary(
        id=document.id,
        document_type=document.document_type,
        title=document.title,
        my_access=access,
        current_version=document.current_version,
        created_by=document.created_by,
        updated_at=document.updated_at,
    )


def rating_out(row: Feedback | None) -> RatingOut | None:
    if row is None or not isinstance(row.value, bool):
        return None
    return RatingOut(rating=row.value, reasons=row.reasons, comment=row.comment)


def field_out(
    spec_path: str,
    catalog: FieldCatalog,
    document: Document,
    row: DocumentField | None,
    ratings: Ratings | None = None,
) -> FieldOut:
    doc_type = catalog.get(document.document_type)
    spec = doc_type.field(spec_path) if doc_type else None
    assert spec is not None
    if row is None:
        return FieldOut(
            field_path=spec.path,
            label=spec.label,
            type=spec.type,
            agent_generates=spec.agent_generates,
        )
    # A rating belongs to the value a run wrote: after a regenerate it no longer applies.
    rated = (ratings or {}).get((row.agent_run_id, spec.path)) if row.agent_run_id else None
    return FieldOut(
        my_rating=rating_out(rated) if row.source == FieldSource.AGENT else None,
        field_path=spec.path,
        label=spec.label,
        type=spec.type,
        agent_generates=spec.agent_generates,
        value=row.value,
        source=FieldSource(row.source),
        confidence=row.confidence,
        confidence_reason=row.confidence_reason,
        reasoning=row.reasoning,
        citations=[CitationOut.model_validate(c) for c in row.citations or []],
        agent_run_id=row.agent_run_id,
        updated_by=row.updated_by,
        updated_at=row.updated_at,
    )


def document_out(
    document: Document,
    access: Access,
    rows: Mapping[str, DocumentField],
    catalog: FieldCatalog,
    active_runs: Sequence[AgentRun],
    ratings: Ratings | None = None,
) -> DocumentOut:
    doc_type = catalog.get(document.document_type)
    paths = [spec.path for spec in doc_type.fields] if doc_type else []
    return DocumentOut(
        **document_summary(document, access).model_dump(),
        fields=[field_out(path, catalog, document, rows.get(path), ratings) for path in paths],
        active_runs=[run_out(run) for run in active_runs],
    )


def run_out(run: AgentRun) -> AgentRunOut:
    suggestion = None
    answer = None
    if run.status == RunStatus.SUCCEEDED and run.response_payload:
        output = AgentRunStatus.model_validate(run.response_payload).output
        if output is not None and run.run_kind == "enhance_field" and output.fields:
            suggestion = SuggestionOut.model_validate(output.fields[0].model_dump(mode="json"))
        if output is not None and output.answer is not None:
            answer = output.answer.content
    enhance_context = (run.request_payload or {}).get("enhance_context") or {}
    return AgentRunOut(
        id=run.id,
        document_id=run.document_id,
        thread_id=run.thread_id,
        run_kind=run.run_kind,
        field_path=enhance_context.get("field_path"),
        status=RunStatus(run.status),
        step_history=[StepOut.model_validate(step) for step in run.step_history or []],
        suggestion=suggestion,
        answer=answer,
        error_code=run.error_code,
        error_message=run.error_message,
        trace_id=run.mlflow_trace_id,
        created_at=run.created_at,
        completed_at=run.completed_at,
    )
