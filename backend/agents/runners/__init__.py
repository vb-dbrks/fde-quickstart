"""Real runners, one per run kind. Each is a LangChain chain: prompt | model.with_structured_output()."""

from backend.agents.llm import ModelFactory
from backend.agents.runners.assistant_turn import make_assistant_turn_runner
from backend.agents.runners.enhance_field import make_enhance_field_runner
from backend.agents.runners.generate import make_generate_runner
from backend.agents.runtime import RunFn
from backend.contracts.agent_contract_v1 import AgentRunKind
from backend.contracts.field_catalog import FieldCatalog


def real_runners(
    model: ModelFactory, catalog: FieldCatalog, *, agent_version: str, model_name: str
) -> dict[AgentRunKind, RunFn]:
    options = {"agent_version": agent_version, "model_name": model_name}
    return {
        "generate": make_generate_runner(model, catalog, **options),
        "enhance_field": make_enhance_field_runner(model, catalog, **options),
        "assistant_turn": make_assistant_turn_runner(model, catalog, **options),
    }
