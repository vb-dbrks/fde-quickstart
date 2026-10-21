"""enhance_field: suggest a revision of one field. The app applies it only if the user accepts."""

from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from backend.agents.llm import ModelFactory
from backend.agents.runners._common import (
    ModelCitation,
    field_payload,
    invoke,
    known_citations,
    load_prompt,
    output_meta,
    shape_value,
    sources_payload,
    to_json,
)
from backend.agents.runtime import AgentRunFailed, RunFn, Steps
from backend.contracts.agent_contract_v1 import AgentOutput, AgentRunRequest, OutputField
from backend.contracts.field_catalog import FieldCatalog

PROMPT = ChatPromptTemplate.from_messages([("system", "{instructions}"), ("human", "{payload}")])


class FieldRevision(BaseModel):
    value: str | list[str] = Field(description="The revised value, in the requested value_type.")
    confidence: Literal["high", "medium", "low"]
    confidence_reason: str = Field(description="One sentence: why this confidence.")
    reasoning: str = Field(description="One sentence: what you changed and why.")
    citations: list[ModelCitation] = Field(default_factory=list)


def make_enhance_field_runner(
    model: ModelFactory, catalog: FieldCatalog, *, agent_version: str, model_name: str
) -> RunFn:
    def run(request: AgentRunRequest, steps: Steps) -> AgentOutput:
        with steps.step("reading_field"):
            context = request.enhance_context
            doc_type = catalog.get(request.document_context.document_type)
            spec = doc_type.field(context.field_path) if doc_type and context else None
            if context is None or spec is None:
                raise AgentRunFailed("OUTPUT_INVALID", "enhance_field needs a known field.")
            payload = {
                "field": field_payload(spec),
                "current_value": context.current_value,
                "instruction": context.instruction or "Make it clearer and more specific.",
                "other_fields": request.document_context.fields,
                "sources": sources_payload(request),
            }
        with steps.step("suggesting_revision"):
            chain = PROMPT | model().with_structured_output(FieldRevision)
            result = invoke(
                chain,
                {"instructions": load_prompt("enhance_field"), "payload": to_json(payload)},
                FieldRevision,
            )
        field = OutputField(
            field_path=spec.path,
            value=shape_value(spec, result.value),
            confidence=result.confidence,
            confidence_reason=result.confidence_reason,
            reasoning=result.reasoning,
            citations=known_citations(result.citations, request),
        )
        return AgentOutput(
            fields=[field], meta=output_meta("enhance_field", agent_version, model_name)
        )

    return run
