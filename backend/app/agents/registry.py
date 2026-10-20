"""The agents this app serves, and where their traces go."""

from collections.abc import Iterable

from agents import set_tracing_disabled

from app.agents.assistant import AssistantAgent
from app.agents.base import AppAgent
from app.config import Settings


class AgentRegistry:
    def __init__(self, members: Iterable[AppAgent]) -> None:
        self._agents = {agent.name: agent for agent in members}

    def get(self, name: str) -> AppAgent | None:
        return self._agents.get(name)

    def all(self) -> list[AppAgent]:
        return list(self._agents.values())


def build_registry(settings: Settings) -> AgentRegistry:
    """Register new agents here."""
    return AgentRegistry([AssistantAgent(settings.llm_endpoint)])


def configure_tracing(settings: Settings) -> None:
    """Send agent traces to the app's MLflow experiment, or turn tracing off if there is none."""
    if not settings.mlflow_experiment_id:
        # Otherwise the Agents SDK tries to export traces to the OpenAI platform.
        set_tracing_disabled(True)
        return
    import mlflow

    mlflow.set_tracking_uri("databricks")
    mlflow.set_experiment(experiment_id=settings.mlflow_experiment_id)
    mlflow.openai.autolog()  # also replaces the Agents SDK's own trace exporter with MLflow's
