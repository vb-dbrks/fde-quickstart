"""The LangChain runners, offline: a scripted chat model stands in for the Databricks endpoint."""

import json
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult
from langchain_core.prompt_values import PromptValue
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel, PrivateAttr

from backend.agents.runners import real_runners
from backend.agents.runners.assistant_turn import AssistantReply
from backend.agents.runners.enhance_field import FieldRevision
from backend.agents.runners.generate import GeneratedField, GeneratedFields
from backend.agents.runtime import AgentRuntime
from backend.contracts.field_catalog import load_field_catalog
from tests.contracts.test_validation import make_request
from tests.helpers import InlineExecutor


class ScriptedModel(BaseChatModel):
    """Returns queued structured outputs (or raises queued exceptions) and records each prompt."""

    _outputs: list[BaseModel | Exception] = PrivateAttr(default_factory=list)
    _prompts: list[list[BaseMessage]] = PrivateAttr(default_factory=list)

    def queue(self, *outputs: BaseModel | Exception) -> "ScriptedModel":
        self._outputs.extend(outputs)
        return self

    @property
    def prompts(self) -> list[list[BaseMessage]]:
        return self._prompts

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(self, messages: list[BaseMessage], *args: Any, **kwargs: Any) -> ChatResult:
        raise NotImplementedError

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Runnable[Any, Any]:
        def respond(prompt: PromptValue) -> Any:
            self._prompts.append(prompt.to_messages())
            result = self._outputs.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

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
    assert run.output.meta.prompt_version == "generate@1"

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
