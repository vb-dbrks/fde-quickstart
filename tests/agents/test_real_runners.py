"""The LangChain runners, offline: a scripted chat model stands in for the Databricks endpoint."""

import json
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatResult
from langchain_core.prompt_values import PromptValue
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel, PrivateAttr

from backend.agents.runners import real_runners
from backend.agents.runners.assistant_turn import AssistantReply
from backend.agents.runners.enhance_field import FieldRevision
from backend.agents.runners.generate import GeneratedField, GeneratedFields
from backend.agents.runtime import AgentRuntime, InlineExecutor
from backend.contracts.agent_contract_v1 import AgentRunKind, AgentRunStatus
from backend.contracts.field_catalog import load_field_catalog
from tests.contracts.test_validation import make_request


class ScriptedModel(BaseChatModel):
    """Answers with queued outputs and records each prompt. A queued schema object becomes a tool
    call with its fields as arguments; a queued AIMessage is returned as it is; an exception is raised.
    """

    _outputs: list[BaseModel | AIMessage | Exception] = PrivateAttr(default_factory=list)
    _prompts: list[list[BaseMessage]] = PrivateAttr(default_factory=list)
    _tool_choices: list[Any] = PrivateAttr(default_factory=list)

    def queue(self, *outputs: BaseModel | AIMessage | Exception) -> "ScriptedModel":
        self._outputs.extend(outputs)
        return self

    @property
    def tool_choices(self) -> list[Any]:
        return self._tool_choices

    @property
    def prompts(self) -> list[list[BaseMessage]]:
        return self._prompts

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(self, messages: list[BaseMessage], *args: Any, **kwargs: Any) -> ChatResult:
        raise NotImplementedError

    def bind_tools(
        self, tools: Any, *, tool_choice: Any = None, **kwargs: Any
    ) -> Runnable[Any, Any]:
        self._tool_choices.append(tool_choice)

        def respond(prompt: PromptValue) -> AIMessage:
            self._prompts.append(prompt.to_messages())
            result = self._outputs.pop(0)
            if isinstance(result, Exception):
                raise result
            if isinstance(result, AIMessage):
                return result
            call = {"name": type(result).__name__, "args": result.model_dump(), "id": "call-1"}
            return AIMessage(content="", tool_calls=[call])

        return RunnableLambda(respond)


def runtime_for(model: ScriptedModel) -> AgentRuntime:
    catalog = load_field_catalog()
    runners = real_runners(lambda: model, catalog, agent_version="test", model_name="scripted")
    return AgentRuntime(runners, catalog=catalog, executor=InlineExecutor())


def generated(path: str, value: Any, *, cite: str | None = None) -> GeneratedField:
    citations = [{"source_document_id": cite, "snippet": "quote"}] if cite else []
    return GeneratedField.model_validate(
        {
            "field_path": path,
            "value": value,
            "confidence": "high",
            "confidence_reason": "stated",
            "reasoning": "because",
            "citations": citations,
        }
    )


def test_generate_maps_model_output_to_contract_fields() -> None:
    model = ScriptedModel().queue(
        GeneratedFields(
            fields=[
                generated("brief.summary", ["Two", "lines"]),  # list for a text field
                generated("brief.key_points", "- one\n- two"),  # text for a list field
                generated("brief.risks", ["r1"], cite="s1"),
                generated("brief.next_steps", ["n1"], cite="invented"),  # unknown source
                generated("brief.title", "not requested"),
            ]
        )
    )
    runtime = runtime_for(model)
    runtime.submit(make_request())
    run = runtime.poll("run-1")
    assert run is not None
    assert run.status == "succeeded", run.error
    assert run.output is not None
    fields = {f.field_path: f for f in run.output.fields}
    assert set(fields) == {"brief.summary", "brief.key_points", "brief.risks", "brief.next_steps"}
    assert fields["brief.summary"].value == "Two\nlines"
    assert fields["brief.key_points"].value == ["one", "two"]
    assert [c.source_document_id for c in fields["brief.risks"].citations] == ["s1"]
    assert fields["brief.next_steps"].citations == []
    assert run.output.meta.runner == "real"
    assert run.output.meta.prompt_version == "generate@2"

    system, human = model.prompts[0]
    payload = json.loads(str(human.content))
    assert "Return every field in `fields_to_write`" in str(system.content)
    assert [f["field_path"] for f in payload["fields_to_write"]] == list(fields)
    assert payload["sources"][0]["source_document_id"] == "s1"


def test_model_failures_become_retryable_model_errors() -> None:
    runtime = runtime_for(ScriptedModel().queue(ConnectionError("endpoint down")))
    runtime.submit(make_request())
    run = runtime.poll("run-1")
    assert run is not None
    assert run.error is not None
    assert (run.error.code, run.error.retryable) == ("MODEL_ERROR", True)
    assert [s.status for s in run.step_history] == ["completed", "failed", "pending"]


def test_enhance_field_returns_one_revised_field() -> None:
    revision = FieldRevision.model_validate(
        {"value": "Better", "confidence": "medium", "confidence_reason": "x", "reasoning": "y"}
    )
    runtime = runtime_for(ScriptedModel().queue(revision))
    runtime.submit(make_request("enhance_field"))
    run = runtime.poll("run-1")
    assert run is not None
    assert run.output is not None
    assert [(f.field_path, f.value) for f in run.output.fields] == [("brief.summary", "Better")]


def test_assistant_turn_sends_the_history_as_chat_messages() -> None:
    model = ScriptedModel().queue(AssistantReply(content="It is fine."))
    runtime = runtime_for(model)
    request = make_request(
        "assistant_turn",
        assistant_context={
            "thread_id": "t",
            "message": "Is it fine?",
            "history": [
                {"role": "user", "content": "Earlier question"},
                {"role": "assistant", "content": "Earlier answer"},
            ],
        },
    )
    runtime.submit(request)
    run = runtime.poll("run-1")
    assert run is not None
    assert run.output is not None
    assert run.output.answer is not None
    assert run.output.answer.content == "It is fine."
    roles = [message.type for message in model.prompts[0]]
    assert roles == ["system", "human", "ai", "human"]


# ---- the reply as a tool call, parsed leniently (some endpoints reject forced tool use) ----------


def run_once(model: ScriptedModel, run_kind: AgentRunKind = "generate") -> AgentRunStatus:
    runtime = runtime_for(model)
    runtime.submit(make_request(run_kind))
    status = runtime.poll("run-1")
    assert status is not None
    return status


def test_the_schema_is_offered_as_a_tool_not_forced() -> None:
    model = ScriptedModel().queue(AssistantReply(content="Yes."))
    assert run_once(model, "assistant_turn").status == "succeeded"
    assert model.tool_choices == ["auto"]


def test_nested_lists_sent_as_json_strings_are_decoded() -> None:
    fields = [generated(path, "text") for path in ("brief.summary", "brief.key_points")]
    fields += [generated(path, ["one"]) for path in ("brief.risks", "brief.next_steps")]
    args = {"fields": json.dumps([field.model_dump() for field in fields])}
    reply = AIMessage(content="", tool_calls=[{"name": "GeneratedFields", "args": args, "id": "1"}])
    run = run_once(ScriptedModel().queue(reply))
    assert run.status == "succeeded", run.error
    assert run.output is not None
    assert {f.field_path for f in run.output.fields} == {f.field_path for f in fields}


def test_json_in_the_text_is_accepted_without_a_tool_call() -> None:
    parts: list[str | dict[str, Any]] = [
        {"type": "text", "text": 'Here you go: {"content": "Plain answer."}'}
    ]
    run = run_once(ScriptedModel().queue(AIMessage(content=parts)), "assistant_turn")
    assert run.status == "succeeded", run.error
    assert run.output is not None
    assert run.output.answer is not None
    assert run.output.answer.content == "Plain answer."


def test_a_value_without_its_confidence_is_kept_at_low_confidence() -> None:
    args = {"value": "Shorter.", "citations": []}  # no confidence, confidence_reason or reasoning
    reply = AIMessage(content="", tool_calls=[{"name": "FieldRevision", "args": args, "id": "1"}])
    run = run_once(ScriptedModel().queue(reply), "enhance_field")
    assert run.status == "succeeded", run.error
    assert run.output is not None
    [field] = run.output.fields
    assert (field.value, field.confidence) == ("Shorter.", "low")
    assert field.confidence_reason == "The model did not give its confidence."


def test_a_reply_that_does_not_parse_is_asked_for_again() -> None:
    mangled = AIMessage(
        content="",
        tool_calls=[{"name": "AssistantReply", "args": {"content": ["not", "text"]}, "id": "1"}],
    )
    model = ScriptedModel().queue(mangled, AssistantReply(content="Second try."))
    run = run_once(model, "assistant_turn")
    assert run.status == "succeeded", run.error
    assert len(model.prompts) == 2


def test_a_reply_with_neither_fails_as_a_model_error() -> None:
    refusal = AIMessage(content="Sorry, I can't.")
    model = ScriptedModel().queue(refusal, refusal)  # the first try and the retry
    run = run_once(model, "assistant_turn")
    assert run.error is not None
    assert (run.status, run.error.code) == ("failed", "MODEL_ERROR")
    assert len(model.prompts) == 2
