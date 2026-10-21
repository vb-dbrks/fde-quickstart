from typing import Any

import pytest
from pydantic import ValidationError

from backend.contracts.agent_contract_v1 import (
    AgentOutput,
    AgentRunRequest,
    AgentRunStatus,
    AssistantAnswer,
    Citation,
    OutputField,
    OutputMeta,
)
from backend.contracts.field_catalog import load_field_catalog
from backend.contracts.validation import check_output, check_request, requested_fields

META = OutputMeta(runner="fake", agent_version="test")


def make_request(run_kind: str = "generate", **context: Any) -> AgentRunRequest:
    defaults: dict[str, Any] = {
        "generate": {"generate_context": {"scope": "all"}},
        "enhance_field": {"enhance_context": {"field_path": "brief.summary"}},
        "assistant_turn": {"assistant_context": {"thread_id": "t", "message": "hi"}},
    }[run_kind]
    return AgentRunRequest.model_validate(
        {
            "app_agent_run_id": "run-1",
            "run_kind": run_kind,
            "idempotency_key": "run-1",
            "document_context": {"document_id": "d", "document_type": "brief", "fields": {}},
            "source_documents": [{"source_document_id": "s1", "title": "Source", "text": "text"}],
            "meta": {"initiator": "a@example.com", "submitted_at": "2026-10-20T00:00:00Z"},
            **(context or defaults),
        }
    )


def field(path: str, value: Any = "text", *, cite: str | None = None) -> OutputField:
    citations = [Citation(source_document_id=cite)] if cite else []
    return OutputField(
        field_path=path,
        value=value,
        confidence="high",
        confidence_reason="r",
        reasoning="r",
        citations=citations,
    )


def test_the_request_context_must_match_the_run_kind() -> None:
    with pytest.raises(ValidationError, match="requires generate_context"):
        make_request("generate", enhance_context={"field_path": "brief.summary"})
    with pytest.raises(ValidationError, match="not allowed for enhance_field"):
        make_request(
            "enhance_field",
            enhance_context={"field_path": "brief.summary"},
            generate_context={"scope": "all"},
        )


def test_terminal_statuses_need_their_payload() -> None:
    base = {"app_agent_run_id": "r", "run_kind": "generate"}
    with pytest.raises(ValidationError, match="must include output"):
        AgentRunStatus.model_validate({**base, "status": "succeeded"})
    with pytest.raises(ValidationError, match="must include error"):
        AgentRunStatus.model_validate({**base, "status": "failed"})


def test_requested_fields_follow_the_scope() -> None:
    catalog = load_field_catalog()
    assert len(requested_fields(make_request(), catalog)) == 4
    scoped = make_request(generate_context={"scope": ["brief.risks", "brief.title"]})
    assert requested_fields(scoped, catalog) == ["brief.risks"]


def test_a_valid_generate_output_passes() -> None:
    output = AgentOutput(
        fields=[field("brief.summary", cite="s1"), field("brief.risks", ["a", "b"])], meta=META
    )
    assert check_output(make_request(), output, load_field_catalog()) == []


@pytest.mark.parametrize(
    ("output", "problem"),
    [
        (AgentOutput(fields=[], meta=META), "no fields"),
        (AgentOutput(fields=[field("brief.title")], meta=META), "was not requested"),
        (AgentOutput(fields=[field("brief.risks", "not a list")], meta=META), "list of strings"),
        (AgentOutput(fields=[field("brief.summary", cite="nope")], meta=META), "unknown source"),
        (
            AgentOutput(fields=[field("brief.summary"), field("brief.summary")], meta=META),
            "repeats",
        ),
    ],
)
def test_invalid_generate_outputs_are_reported(output: AgentOutput, problem: str) -> None:
    problems = check_output(make_request(), output, load_field_catalog())
    assert any(problem in p for p in problems), problems


def test_enhance_field_returns_exactly_the_requested_field() -> None:
    request = make_request("enhance_field")
    catalog = load_field_catalog()
    assert (
        check_output(request, AgentOutput(fields=[field("brief.summary")], meta=META), catalog)
        == []
    )
    wrong = AgentOutput(fields=[field("brief.risks", ["x"])], meta=META)
    assert check_output(request, wrong, catalog)


def test_assistant_turns_answer_without_fields() -> None:
    request = make_request("assistant_turn")
    catalog = load_field_catalog()
    good = AgentOutput(answer=AssistantAnswer(content="Answer"), meta=META)
    assert check_output(request, good, catalog) == []
    assert check_output(request, AgentOutput(meta=META), catalog)
    assert check_output(
        request,
        AgentOutput(
            answer=AssistantAnswer(content="x"), fields=[field("brief.summary")], meta=META
        ),
        catalog,
    )


def test_requests_for_unknown_fields_are_rejected() -> None:
    catalog = load_field_catalog()
    assert check_request(
        make_request("enhance_field", enhance_context={"field_path": "brief.title"}), catalog
    )
    assert check_request(make_request(generate_context={"scope": ["brief.nope"]}), catalog)
