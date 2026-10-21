"""generate: draft every requested agent field of a document, with confidence and citations."""

from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field, model_validator

from backend.agents.llm import ModelFactory
from backend.agents.runners._common import (
    ModelCitation,
    field_payload,
    fill_missing_metadata,
    invoke,
    known_citations,
    load_prompt,
    output_meta,
    shape_value,
    sources_payload,
    structured,
    to_json,
)
from backend.agents.runtime import AgentRunFailed, RunFn, Steps
from backend.contracts.agent_contract_v1 import AgentOutput, AgentRunRequest, OutputField
from backend.contracts.field_catalog import FieldCatalog
from backend.contracts.validation import requested_fields

PROMPT = ChatPromptTemplate.from_messages([("system", "{instructions}"), ("human", "{payload}")])


class GeneratedField(BaseModel):
    field_path: str = Field(description="One of the requested field paths, exactly as given.")
    value: str | list[str] = Field(description="The field value, in the requested value_type.")
    confidence: Literal["high", "medium", "low"]
    confidence_reason: str = Field(description="One sentence: why this confidence.")
    reasoning: str = Field(description="One or two sentences: how you arrived at the value.")
    citations: list[ModelCitation] = Field(default_factory=list)

    _fill_missing_metadata = model_validator(mode="before")(fill_missing_metadata)


class GeneratedFields(BaseModel):
    fields: list[GeneratedField]


def make_generate_runner(
    model: ModelFactory, catalog: FieldCatalog, *, agent_version: str, model_name: str
) -> RunFn:
    def run(request: AgentRunRequest, steps: Steps) -> AgentOutput:
        with steps.step("reading_context"):
            doc_type = catalog.get(request.document_context.document_type)
            paths = requested_fields(request, catalog)
            if doc_type is None or not paths:
                raise AgentRunFailed("OUTPUT_INVALID", "Nothing to generate for this request.")
            specs = {path: spec for path in paths if (spec := doc_type.field(path)) is not None}
            payload = {
                "document_type": doc_type.label,
                "document_description": doc_type.description,
                "current_fields": request.document_context.fields,
                "instruction": request.document_context.user_instruction,
                "fields_to_write": [field_payload(spec) for spec in specs.values()],
                "sources": sources_payload(request),
            }
        with steps.step("drafting_fields"):
            chain = PROMPT | structured(model(), GeneratedFields)
            result = invoke(
                chain,
                {"instructions": load_prompt("generate"), "payload": to_json(payload)},
                GeneratedFields,
            )
        with steps.step("checking_citations"):
            fields = [
                OutputField(
                    field_path=item.field_path,
                    value=shape_value(specs[item.field_path], item.value),
                    confidence=item.confidence,
                    confidence_reason=item.confidence_reason,
                    reasoning=item.reasoning,
                    citations=known_citations(item.citations, request),
                )
                for item in result.fields
                if item.field_path in specs
            ]
        return AgentOutput(fields=fields, meta=output_meta("generate", agent_version, model_name))

    return run
