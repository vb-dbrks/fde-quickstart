"""assistant_turn: answer one chat message about a document, given the history the app sends."""

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from pydantic import BaseModel, Field

from backend.agents.llm import ModelFactory
from backend.agents.runners._common import (
    ModelCitation,
    invoke,
    known_citations,
    load_prompt,
    output_meta,
    sources_payload,
    to_json,
)
from backend.agents.runtime import AgentRunFailed, RunFn, Steps
from backend.contracts.agent_contract_v1 import AgentOutput, AgentRunRequest, AssistantAnswer
from backend.contracts.field_catalog import FieldCatalog

PROMPT = ChatPromptTemplate.from_messages(
    [("system", "{instructions}"), MessagesPlaceholder("history"), ("human", "{payload}")]
)


class AssistantReply(BaseModel):
    content: str = Field(description="The answer, in plain text without Markdown.")
    citations: list[ModelCitation] = Field(default_factory=list)


def make_assistant_turn_runner(
    model: ModelFactory, catalog: FieldCatalog, *, agent_version: str, model_name: str
) -> RunFn:
    def run(request: AgentRunRequest, steps: Steps) -> AgentOutput:
        with steps.step("reading_conversation"):
            context = request.assistant_context
            if context is None:
                raise AgentRunFailed("OUTPUT_INVALID", "assistant_turn needs assistant_context.")
            history: list[BaseMessage] = [
                HumanMessage(m.content) if m.role == "user" else AIMessage(m.content)
                for m in context.history
            ]
            doc_type = catalog.get(request.document_context.document_type)
            payload = {
                "question": context.message,
                "document_type": doc_type.label
                if doc_type
                else request.document_context.document_type,
                "document_fields": request.document_context.fields,
                "sources": sources_payload(request),
                "earlier_messages_omitted": context.history_truncated,
            }
        with steps.step("composing_answer"):
            chain = PROMPT | model().with_structured_output(AssistantReply)
            reply = invoke(
                chain,
                {
                    "instructions": load_prompt("assistant_turn"),
                    "history": history,
                    "payload": to_json(payload),
                },
                AssistantReply,
            )
        answer = AssistantAnswer(
            content=reply.content, citations=known_citations(reply.citations, request)
        )
        return AgentOutput(
            answer=answer, meta=output_meta("assistant_turn", agent_version, model_name)
        )

    return run
