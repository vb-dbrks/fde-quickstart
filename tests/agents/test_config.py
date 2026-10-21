import databricks_langchain
import pytest

from backend.agents.llm import chat_model_factory
from backend.agents.runtime import InlineExecutor
from backend.agents.server import build_runtime
from tests.helpers import IsolatedAgentSettings


def test_runners_default_to_fake_without_an_endpoint() -> None:
    settings = IsolatedAgentSettings(llm_endpoint=None, agent_runner=None)
    assert set(settings.runner_choices().values()) == {"fake"}


def test_an_endpoint_makes_the_real_runners_the_default() -> None:
    settings = IsolatedAgentSettings(llm_endpoint="my-endpoint", agent_runner=None)
    assert set(settings.runner_choices().values()) == {"real"}


def test_overrides_pick_runners_per_run_kind() -> None:
    settings = IsolatedAgentSettings(
        llm_endpoint="my-endpoint",
        agent_runner="fake",
        agent_runner_overrides="assistant_turn=real, generate = fake",
    )
    assert settings.runner_choices() == {
        "generate": "fake",
        "enhance_field": "fake",
        "assistant_turn": "real",
    }


def test_real_runners_need_an_endpoint() -> None:
    settings = IsolatedAgentSettings(llm_endpoint=None, agent_runner="real")
    with pytest.raises(RuntimeError, match="needs LLM_ENDPOINT"):
        build_runtime(settings, executor=InlineExecutor())


def test_mixed_runtimes_report_their_runners() -> None:
    settings = IsolatedAgentSettings(
        llm_endpoint="my-endpoint",
        agent_runner="fake",
        agent_runner_overrides="assistant_turn=real",
    )
    runtime = build_runtime(settings, executor=InlineExecutor())
    assert runtime.runner_names["assistant_turn"] == "real"


def test_the_model_gets_no_temperature_unless_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """Some endpoints (recent Claude models) answer 400 BAD_REQUEST to any temperature."""
    created: list[dict[str, object]] = []
    monkeypatch.setattr(databricks_langchain, "ChatDatabricks", lambda **kw: created.append(kw))
    chat_model_factory("my-endpoint")()
    chat_model_factory("my-endpoint", temperature=0.3)()
    assert created == [
        {"endpoint": "my-endpoint", "temperature": None},
        {"endpoint": "my-endpoint", "temperature": 0.3},
    ]
