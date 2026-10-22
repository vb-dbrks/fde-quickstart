"""Deterministic runners that follow the contract exactly, including the step names.

Knobs (AgentSettings / environment):

  FAKE_AGENT_STEP_SECONDS  seconds per step (default 1.0; 0 in tests)
  FAKE_AGENT_FAIL_AT       a step name; the run fails there with MODEL_ERROR (retryable)
  FAKE_AGENT_VERSION       reported as output.meta.agent_version
  FAKE_AGENT_DRIFT         prefixed to every generated string, so a replay against this build
                           produces different output than the stored one
"""

import time
from dataclasses import dataclass

from backend.agents.runtime import AgentRunFailed, RunFn, Steps
from backend.contracts.agent_contract_v1 import (
    STEP_VOCABULARY,
    AgentOutput,
    AgentRunKind,
    AgentRunRequest,
    AssistantAnswer,
    Citation,
    OutputField,
    OutputMeta,
    UIAction,
)
from backend.contracts.field_catalog import FieldCatalog, FieldSpec
from backend.contracts.validation import requested_fields


@dataclass(frozen=True)
class FakeAgent:
    catalog: FieldCatalog
    step_seconds: float = 1.0
    fail_at: str | None = None
    version: str = "fake-agent"
    drift: str = ""

    def runners(self) -> dict[AgentRunKind, RunFn]:
        return {
            "generate": self.generate,
            "enhance_field": self.enhance_field,
            "assistant_turn": self.assistant_turn,
        }

    # ---- run kinds ---------------------------------------------------------------------------

    def generate(self, request: AgentRunRequest, steps: Steps) -> AgentOutput:
        self._walk(request, steps)
        doc_type = self.catalog.get(request.document_context.document_type)
        title = self._title(request)
        fields = []
        for path in requested_fields(request, self.catalog):
            spec = doc_type.field(path) if doc_type else None
            if spec is None:
                continue
            fields.append(
                self._field(
                    spec, self._draft(spec, title), request, "Drafted from the title and goal."
                )
            )
        from backend.agents.runners._common import preview_callback

        callback = preview_callback.get()
        if callback:
            for i in range(1, len(fields) + 1):
                callback({"fields": [f.model_dump(mode="json") for f in fields[:i]]}, False)
                if self.step_seconds:
                    time.sleep(self.step_seconds / 4)
        return AgentOutput(fields=fields, meta=self._meta())

    def enhance_field(self, request: AgentRunRequest, steps: Steps) -> AgentOutput:
        self._walk(request, steps)
        context = request.enhance_context
        doc_type = self.catalog.get(request.document_context.document_type)
        spec = doc_type.field(context.field_path) if doc_type and context else None
        if context is None or spec is None:
            raise AgentRunFailed("OUTPUT_INVALID", "enhance_field needs a known field")
        instruction = context.instruction or "clearer wording"
        if spec.type == "list":
            current = context.current_value if isinstance(context.current_value, list) else []
            value: str | list[str] = [*current, f"{self.drift}Added for: {instruction}"]
        else:
            current_text = context.current_value if isinstance(context.current_value, str) else ""
            value = f"{self.drift}{current_text} (revised: {instruction})".strip()
        return AgentOutput(
            fields=[self._field(spec, value, request, f"Applied the instruction: {instruction}.")],
            meta=self._meta(),
        )

    def assistant_turn(self, request: AgentRunRequest, steps: Steps) -> AgentOutput:
        self._walk(request, steps)
        context = request.assistant_context
        if context is None:
            raise AgentRunFailed("OUTPUT_INVALID", "assistant_turn needs assistant_context")
        content = (
            f"{self.drift}(Fake agent) You asked: “{context.message}”. I can see "
            f"{len(context.history)} earlier messages and {len(request.source_documents)} source "
            f"documents for “{self._title(request)}”."
        )
        doc_type = self.catalog.get(request.document_context.document_type)
        focus = (
            next(
                (f.path for f in doc_type.fields if f.label.lower() in context.message.lower()),
                None,
            )
            if doc_type
            else None
        )
        return AgentOutput(
            ui_action=UIAction(field_path=focus) if focus else None,
            answer=AssistantAnswer(content=content, citations=self._citations(request)),
            meta=self._meta(),
        )

    # ---- helpers -----------------------------------------------------------------------------

    def _walk(self, request: AgentRunRequest, steps: Steps) -> None:
        for name in STEP_VOCABULARY[request.run_kind]:
            with steps.step(name):
                if self.step_seconds > 0:
                    time.sleep(self.step_seconds)
                if self.fail_at == name:
                    raise AgentRunFailed(
                        "MODEL_ERROR", f"Fake agent failure injected at {name}.", retryable=True
                    )

    def _title(self, request: AgentRunRequest) -> str:
        fields = request.document_context.fields
        title = fields.get(f"{request.document_context.document_type}.title")
        return str(title) if title else "Untitled"

    def _draft(self, spec: FieldSpec, title: str) -> str | list[str]:
        if spec.type == "list":
            return [f"{self.drift}{spec.label} {n} for “{title}”" for n in (1, 2, 3)]
        return f"{self.drift}{spec.label} for “{title}”, drafted by the fake agent."

    def _citations(self, request: AgentRunRequest) -> list[Citation]:
        if not request.source_documents:
            return []
        source = request.source_documents[0]
        return [Citation(source_document_id=source.source_document_id, snippet=source.text[:120])]

    def _field(
        self, spec: FieldSpec, value: str | list[str], request: AgentRunRequest, reasoning: str
    ) -> OutputField:
        return OutputField(
            field_path=spec.path,
            value=value,
            confidence="medium",
            confidence_reason="The fake agent always reports medium confidence.",
            reasoning=f"Fake agent: {reasoning}",
            citations=self._citations(request),
        )

    def _meta(self) -> OutputMeta:
        return OutputMeta(runner="fake", agent_version=self.version)
