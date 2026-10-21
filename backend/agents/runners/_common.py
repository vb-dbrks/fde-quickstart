"""Shared pieces of the real runners: prompts, model output schemas and contract mapping."""

import json
import logging
from functools import cache
from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import BaseModel, Field

from backend.agents.runtime import AgentRunFailed
from backend.contracts.agent_contract_v1 import AgentRunRequest, Citation, OutputMeta
from backend.contracts.field_catalog import FieldSpec

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
# Bump when a prompt changes, so traces and outputs say which prompt produced them.
PROMPT_VERSIONS = {
    "generate": "generate@2",
    "enhance_field": "enhance_field@2",
    "assistant_turn": "assistant_turn@2",
}


@cache
def load_prompt(run_kind: str) -> str:
    return (PROMPTS_DIR / f"{run_kind}.md").read_text()


class ModelCitation(BaseModel):
    source_document_id: str = Field(description="The source_document_id of a provided source.")
    snippet: str = Field(description="A short quote from that source supporting the value.")


def sources_payload(request: AgentRunRequest) -> list[dict[str, str]]:
    return [
        {"source_document_id": s.source_document_id, "title": s.title, "text": s.text}
        for s in request.source_documents
    ]


def field_payload(spec: FieldSpec) -> dict[str, str]:
    shape = "a string" if spec.type == "text" else "a list of short strings"
    return {
        "field_path": spec.path,
        "label": spec.label,
        "value_type": shape,
        "description": spec.description,
    }


def to_json(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str)


def known_citations(citations: list[ModelCitation], request: AgentRunRequest) -> list[Citation]:
    """Keep citations of provided sources; the model sometimes invents ids."""
    allowed = {source.source_document_id for source in request.source_documents}
    kept = [
        Citation(source_document_id=c.source_document_id, snippet=c.snippet)
        for c in citations
        if c.source_document_id in allowed
    ]
    if len(kept) < len(citations):
        logger.info("Dropped %d citations of unknown sources", len(citations) - len(kept))
    return kept


def shape_value(spec: FieldSpec, value: str | list[str]) -> str | list[str]:
    """Coerce a model value to the catalog type (text <-> list) instead of failing the run."""
    if spec.type == "text":
        return "\n".join(value) if isinstance(value, list) else value
    if isinstance(value, str):
        return [line.lstrip("-* ").strip() for line in value.splitlines() if line.strip()]
    return value


def structured[SchemaT: BaseModel](
    model: BaseChatModel, schema: type[SchemaT]
) -> Runnable[Any, SchemaT]:
    """The model's answer as ``schema``, from a tool call the model is asked - not forced - to make.

    ``with_structured_output()`` forces the tool call or sends ``response_format``, and newer Anthropic
    models on Databricks reject both (400 BAD_REQUEST). So the schema is bound as a tool with
    ``tool_choice="auto"``, the prompts tell the model to call it, and the reply is parsed leniently.
    A reply that still doesn't parse (now and then the model mangles nested JSON) is asked for once
    more.
    """
    name = convert_to_openai_tool(schema)["function"]["name"]

    def parse(message: AIMessage) -> SchemaT:
        return parse_structured(message, schema, tool_name=name)

    chain = model.bind_tools([schema], tool_choice="auto") | RunnableLambda(parse)
    # ValueError covers pydantic's ValidationError and json.JSONDecodeError. Nothing to wait out: retry
    # at once.
    return chain.with_retry(
        retry_if_exception_type=(ValueError,), stop_after_attempt=2, wait_exponential_jitter=False
    )


def parse_structured[SchemaT: BaseModel](
    message: AIMessage, schema: type[SchemaT], *, tool_name: str
) -> SchemaT:
    """Validate the tool call's arguments, or a JSON object in the text if the model wrote one.

    Models sometimes send nested lists and objects as JSON-encoded strings; those are decoded first.
    """
    for call in message.tool_calls:
        if call["name"] == tool_name:
            return schema.model_validate(_decode_nested_json(call["args"]))
    text = message.text
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ValueError(f"the model neither called {tool_name} nor returned JSON")
    return schema.model_validate(_decode_nested_json(json.loads(text[start : end + 1])))


def fill_missing_metadata(data: Any) -> Any:
    """For a field's ``model_validator(mode="before")``: models now and then return a value without
    its confidence or reasoning. Keep the value and say so, rather than failing the run. The schema
    the model sees still marks these as required."""
    if isinstance(data, dict):
        defaults = {
            "confidence": "low",
            "confidence_reason": "The model did not give its confidence.",
            "reasoning": "",
        }
        return {**defaults, **data}
    return data


def _decode_nested_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _decode_nested_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decode_nested_json(item) for item in value]
    if isinstance(value, str) and value.lstrip()[:1] in ("[", "{"):
        for candidate in (value, _close_brackets(value)):
            try:
                return _decode_nested_json(json.loads(candidate))
            except ValueError:
                continue
        return value  # text that merely starts with a bracket
    return value


def _close_brackets(text: str) -> str:
    """Append the closing brackets a JSON string is missing - models sometimes stop one or two short
    when they encode nested JSON as a string."""
    closers = {"[": "]", "{": "}"}
    open_brackets: list[str] = []
    in_string = escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in closers:
            open_brackets.append(closers[char])
        elif char in "]}" and open_brackets:
            open_brackets.pop()
    return text if in_string else text + "".join(reversed(open_brackets))


def invoke[SchemaT: BaseModel](
    chain: Runnable[Any, Any], inputs: dict[str, Any], schema: type[SchemaT]
) -> SchemaT:
    """Run a structured-output chain; model or parsing failures become MODEL_ERROR (retryable)."""
    try:
        result = chain.invoke(inputs)
    except Exception as exc:
        logger.warning("Model call failed: %s", exc, exc_info=True)
        raise AgentRunFailed(
            "MODEL_ERROR", "The model endpoint returned an error.", retryable=True
        ) from exc
    if not isinstance(result, schema):
        raise AgentRunFailed("MODEL_ERROR", "The model returned no usable output.", retryable=True)
    return result


def output_meta(run_kind: str, agent_version: str, model_name: str) -> OutputMeta:
    return OutputMeta(
        runner="real",
        agent_version=agent_version,
        model=model_name,
        prompt_version=PROMPT_VERSIONS[run_kind],
    )
