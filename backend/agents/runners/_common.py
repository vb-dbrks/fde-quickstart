"""Shared pieces of the real runners: prompts, model output schemas and contract mapping."""

import json
import logging
from functools import cache
from pathlib import Path
from typing import Any

from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

from backend.agents.runtime import AgentRunFailed
from backend.contracts.agent_contract_v1 import AgentRunRequest, Citation, OutputMeta
from backend.contracts.field_catalog import FieldSpec

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
# Bump when a prompt changes, so traces and outputs say which prompt produced them.
PROMPT_VERSIONS = {
    "generate": "generate@1",
    "enhance_field": "enhance_field@1",
    "assistant_turn": "assistant_turn@1",
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
