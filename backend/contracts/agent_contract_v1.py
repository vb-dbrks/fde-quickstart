"""Agent API contract, version 1: the wire format between the app and the agent runtime.

Async submit/poll (ADR 0003): ``POST /agent/run`` takes an ``AgentRunRequest`` and returns an
``AgentRunStatus`` in status ``accepted``; ``GET /agent/run/{app_agent_run_id}`` returns the latest
status until it is ``succeeded`` or ``failed``.

Stateless (ADR 0004): every request carries all the context the agent needs. The agent keeps nothing
between runs; the app stores the request and the result and materialises the output.

These models are frozen. Additive, optional fields are allowed in v1; anything else is a new version.
Change contracts/agent-api-contract.md (the golden record), these models and the fake runner in the
same pull request - tests/contracts fail otherwise.
"""

from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

AGENT_CONTRACT_VERSION = "v1"

AgentRunKind = Literal["generate", "enhance_field", "assistant_turn"]
AgentRunStatusValue = Literal["accepted", "running", "succeeded", "failed"]
StepStatus = Literal["pending", "running", "completed", "failed"]
Confidence = Literal["high", "medium", "low"]

RUN_KINDS: tuple[AgentRunKind, ...] = ("generate", "enhance_field", "assistant_turn")

# Step names per run kind, in order. The UI shows them as progress; both runners must use them.
STEP_VOCABULARY: dict[AgentRunKind, tuple[str, ...]] = {
    "generate": ("reading_context", "drafting_fields", "checking_citations"),
    "enhance_field": ("reading_field", "suggesting_revision"),
    "assistant_turn": ("reading_conversation", "composing_answer"),
}

ERROR_CODES = (
    "VALIDATION_ERROR",  # the request did not match the contract (HTTP 400)
    "RUN_NOT_FOUND",  # unknown app_agent_run_id, e.g. the agent restarted (HTTP 404)
    "MODEL_ERROR",  # the model endpoint failed or returned nothing usable
    "OUTPUT_INVALID",  # the agent produced output that breaks the contract or the catalog
    "INTERNAL_ERROR",  # anything else
)

MAX_SOURCE_TEXT = 20_000


class _ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ---------- request -------------------------------------------------------------------------------


class DocumentContext(_ContractModel):
    document_id: str
    document_type: str
    # Current value of every field, keyed by field path (see contracts/field-catalog.yaml).
    fields: dict[str, Any] = Field(default_factory=dict)
    user_instruction: str | None = None


class GenerateContext(_ContractModel):
    # "all" agent-generated fields, or a subset to regenerate.
    scope: Literal["all"] | list[str] = "all"


class EnhanceFieldContext(_ContractModel):
    field_path: str
    current_value: Any = None
    instruction: str | None = None


class HistoryMessage(_ContractModel):
    role: Literal["user", "assistant"]
    content: str


class AssistantContext(_ContractModel):
    thread_id: str
    message: str
    # Earlier turns, oldest first. The app truncates long conversations.
    history: list[HistoryMessage] = Field(default_factory=list)
    history_truncated: bool = False


class SourceDocument(_ContractModel):
    """A document the user allowed the agent to use. The agent may cite only these."""

    source_document_id: str
    title: str
    text: str = Field(max_length=MAX_SOURCE_TEXT)


class RequestMeta(_ContractModel):
    initiator: str
    submitted_at: str
    app_version: str | None = None


class AgentRunRequest(_ContractModel):
    app_agent_run_id: str
    run_kind: AgentRunKind
    idempotency_key: str
    document_context: DocumentContext
    generate_context: GenerateContext | None = None
    enhance_context: EnhanceFieldContext | None = None
    assistant_context: AssistantContext | None = None
    source_documents: list[SourceDocument] = Field(default_factory=list)
    meta: RequestMeta

    @model_validator(mode="after")
    def _context_matches_run_kind(self) -> Self:
        required = {
            "generate": "generate_context",
            "enhance_field": "enhance_context",
            "assistant_turn": "assistant_context",
        }[self.run_kind]
        for name in ("generate_context", "enhance_context", "assistant_context"):
            present = getattr(self, name) is not None
            if name == required and not present:
                raise ValueError(f"{self.run_kind} requires {name}")
            if name != required and present:
                raise ValueError(f"{name} is not allowed for {self.run_kind}")
        return self


# ---------- response ------------------------------------------------------------------------------


class AgentStep(_ContractModel):
    name: str
    status: StepStatus
    started_at: str | None = None
    completed_at: str | None = None


class Citation(_ContractModel):
    source_document_id: str
    snippet: str | None = None


class OutputField(_ContractModel):
    field_path: str
    value: Any
    confidence: Confidence
    confidence_reason: str
    reasoning: str
    citations: list[Citation] = Field(default_factory=list)


class AssistantAnswer(_ContractModel):
    content: str
    citations: list[Citation] = Field(default_factory=list)


class OutputMeta(_ContractModel):
    runner: Literal["fake", "real"]
    agent_version: str
    model: str | None = None
    prompt_version: str | None = None


class AgentOutput(_ContractModel):
    # generate: the generated fields; enhance_field: exactly one suggested field.
    fields: list[OutputField] = Field(default_factory=list)
    # assistant_turn only.
    answer: AssistantAnswer | None = None
    meta: OutputMeta


class AgentError(_ContractModel):
    code: str
    message: str
    retryable: bool = False


class AgentRunStatus(_ContractModel):
    contract_version: Literal["v1"] = "v1"
    app_agent_run_id: str
    run_kind: AgentRunKind
    status: AgentRunStatusValue
    step_history: list[AgentStep] = Field(default_factory=list)
    output: AgentOutput | None = None
    error: AgentError | None = None
    trace_id: str | None = None

    @model_validator(mode="after")
    def _terminal_payload(self) -> Self:
        if self.status == "succeeded" and self.output is None:
            raise ValueError("a succeeded run must include output")
        if self.status == "failed" and self.error is None:
            raise ValueError("a failed run must include error")
        return self


class AgentErrorEnvelope(_ContractModel):
    """Body of non-2xx responses (400 VALIDATION_ERROR, 404 RUN_NOT_FOUND)."""

    error: AgentError


def contract_document() -> dict[str, Any]:
    """What GET /contract returns: the version and the JSON schemas of both envelopes."""
    return {
        "contract_version": AGENT_CONTRACT_VERSION,
        "run_kinds": list(RUN_KINDS),
        "step_vocabulary": {kind: list(steps) for kind, steps in STEP_VOCABULARY.items()},
        "error_codes": list(ERROR_CODES),
        "request_schema": AgentRunRequest.model_json_schema(),
        "status_schema": AgentRunStatus.model_json_schema(),
    }
