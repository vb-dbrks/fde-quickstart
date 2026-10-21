"""Builds the full-context agent request for a run from the app's own data (ADR 0004)."""

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from backend.contracts.agent_contract_v1 import (
    MAX_SOURCE_TEXT,
    AgentRunKind,
    AgentRunRequest,
    AssistantContext,
    DocumentContext,
    EnhanceFieldContext,
    GenerateContext,
    HistoryMessage,
    RequestMeta,
    SourceDocument,
)
from backend.contracts.field_catalog import FieldCatalog
from backend.domain.models import Document

APP_VERSION = "0.1.0"


def render_source(
    document: Document, fields: Mapping[str, Any], catalog: FieldCatalog
) -> SourceDocument:
    """A document the user picked as a source, flattened to labelled text."""
    doc_type = catalog.get(document.document_type)
    lines: list[str] = []
    for spec in doc_type.fields if doc_type else ():
        value = fields.get(spec.path)
        if value in (None, "", []):
            continue
        text = "; ".join(value) if isinstance(value, list) else str(value)
        lines.append(f"{spec.label}: {text}")
    return SourceDocument(
        source_document_id=document.id,
        title=document.title,
        text="\n".join(lines)[:MAX_SOURCE_TEXT],
    )


def build_request(
    *,
    run_id: str,
    run_kind: AgentRunKind,
    document: Document,
    fields: Mapping[str, Any],
    initiator: str,
    idempotency_key: str | None = None,
    instruction: str | None = None,
    scope: Sequence[str] | None = None,
    field_path: str | None = None,
    thread_id: str | None = None,
    message: str | None = None,
    history: Sequence[tuple[str, str]] = (),
    history_truncated: bool = False,
    sources: Sequence[SourceDocument] = (),
) -> AgentRunRequest:
    context: dict[str, Any] = {}
    if run_kind == "generate":
        context["generate_context"] = GenerateContext(scope=list(scope) if scope else "all")
    elif run_kind == "enhance_field":
        context["enhance_context"] = EnhanceFieldContext(
            field_path=field_path or "",
            current_value=fields.get(field_path or ""),
            instruction=instruction,
        )
    else:
        context["assistant_context"] = AssistantContext(
            thread_id=thread_id or "",
            message=message or "",
            history=[HistoryMessage(role=role, content=content) for role, content in history],
            history_truncated=history_truncated,
        )
    return AgentRunRequest(
        app_agent_run_id=run_id,
        run_kind=run_kind,
        idempotency_key=idempotency_key or run_id,
        document_context=DocumentContext(
            document_id=document.id,
            document_type=document.document_type,
            fields=dict(fields),
            user_instruction=instruction if run_kind == "generate" else None,
        ),
        source_documents=list(sources),
        meta=RequestMeta(
            initiator=initiator,
            submitted_at=datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            app_version=APP_VERSION,
        ),
        **context,
    )
