"""Checks an agent's output against its request and the field catalog.

The agent runtime runs these checks before reporting ``succeeded`` (a failed check becomes
``OUTPUT_INVALID``); the app runs them again before materialising, as defence in depth.
"""

from backend.contracts.agent_contract_v1 import AgentOutput, AgentRunRequest, Citation
from backend.contracts.field_catalog import FieldCatalog


def requested_fields(request: AgentRunRequest, catalog: FieldCatalog) -> list[str]:
    """Field paths the agent is expected to return for this request."""
    doc_type = catalog.get(request.document_context.document_type)
    if doc_type is None:
        return []
    if request.run_kind == "enhance_field" and request.enhance_context is not None:
        return [request.enhance_context.field_path]
    if request.run_kind == "generate" and request.generate_context is not None:
        scope = request.generate_context.scope
        agent_paths = [spec.path for spec in doc_type.agent_fields]
        return agent_paths if scope == "all" else [p for p in agent_paths if p in scope]
    return []


def _check_citations(
    citations: list[Citation], allowed: set[str], where: str, problems: list[str]
) -> None:
    for citation in citations:
        if citation.source_document_id not in allowed:
            problems.append(f"{where} cites unknown source {citation.source_document_id!r}")


def check_request(request: AgentRunRequest, catalog: FieldCatalog) -> list[str]:
    """Problems with a request that the Pydantic models can't see (catalog rules)."""
    doc_type = catalog.get(request.document_context.document_type)
    if doc_type is None:
        return [f"unknown document type {request.document_context.document_type!r}"]
    problems: list[str] = []
    if request.enhance_context is not None:
        spec = doc_type.field(request.enhance_context.field_path)
        if spec is None or not spec.agent_generates:
            problems.append(f"{request.enhance_context.field_path!r} is not an agent field")
    if request.generate_context is not None and request.generate_context.scope != "all":
        unknown = [p for p in request.generate_context.scope if doc_type.field(p) is None]
        if unknown:
            problems.append(f"unknown fields in scope: {unknown}")
    return problems


def check_output(request: AgentRunRequest, output: AgentOutput, catalog: FieldCatalog) -> list[str]:
    """Problems with ``output``; an empty list means it satisfies the contract."""
    problems: list[str] = []
    allowed_sources = {source.source_document_id for source in request.source_documents}
    doc_type = catalog.get(request.document_context.document_type)
    if doc_type is None:
        return [f"unknown document type {request.document_context.document_type!r}"]

    if request.run_kind == "assistant_turn":
        if output.answer is None or not output.answer.content.strip():
            problems.append("assistant_turn output must include a non-empty answer")
        else:
            _check_citations(output.answer.citations, allowed_sources, "answer", problems)
        if output.fields:
            problems.append("assistant_turn output must not include fields")
        return problems

    expected = requested_fields(request, catalog)
    returned = [field.field_path for field in output.fields]
    if not returned:
        problems.append("output contains no fields")
    if len(returned) != len(set(returned)):
        problems.append("output repeats a field")
    for field in output.fields:
        if field.field_path not in expected:
            problems.append(f"{field.field_path!r} was not requested")
            continue
        spec = doc_type.field(field.field_path)
        if spec is None:
            continue
        try:
            spec.coerce(field.value)
        except ValueError as exc:
            problems.append(str(exc))
        _check_citations(field.citations, allowed_sources, field.field_path, problems)
    if request.run_kind == "enhance_field" and len(returned) != 1:
        problems.append("enhance_field output must contain exactly one field")
    if output.answer is not None:
        problems.append(f"{request.run_kind} output must not include an answer")
    return problems
