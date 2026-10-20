"""Example agent: answers questions about the team's notes and can create notes.

Built with the OpenAI Agents SDK on a Databricks Model Serving endpoint (LLM_ENDPOINT). To add an agent,
copy this file, write its prompt in prompts/<name>.md and register it in app.agents.registry.
"""

from collections.abc import Callable
from functools import cache
from pathlib import Path

from agents import Agent, OpenAIChatCompletionsModel, Runner
from openai import AsyncOpenAI

from app.agents.base import AgentContext, AgentNotConfiguredError, AgentReply
from app.agents.llm import databricks_openai_client
from app.agents.tools import TOOLS

PROMPTS_DIR = Path(__file__).parent / "prompts"
MAX_TURNS = 8


@cache
def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text()


class AssistantAgent:
    name = "assistant"
    description = "Answers questions about your team's notes and can create notes for you."

    def __init__(
        self,
        endpoint: str | None,
        client_factory: Callable[[], AsyncOpenAI] = databricks_openai_client,
    ) -> None:
        self._endpoint = endpoint
        self._client_factory = client_factory
        self._agent: Agent[AgentContext] | None = None

    @property
    def configured(self) -> bool:
        return bool(self._endpoint)

    def build(self) -> Agent[AgentContext]:
        """The underlying Agents SDK agent, created on first use."""
        if self._agent is None:
            if not self._endpoint:
                raise AgentNotConfiguredError(
                    "The assistant is not configured: set LLM_ENDPOINT to a Model Serving endpoint."
                )
            model = OpenAIChatCompletionsModel(
                model=self._endpoint, openai_client=self._client_factory()
            )
            self._agent = Agent[AgentContext](
                name=self.name,
                instructions=load_prompt(self.name),
                model=model,
                tools=list(TOOLS),
            )
        return self._agent

    async def run(self, context: AgentContext, message: str) -> AgentReply:
        result = await Runner.run(self.build(), message, context=context, max_turns=MAX_TURNS)
        return AgentReply(output=str(result.final_output))
