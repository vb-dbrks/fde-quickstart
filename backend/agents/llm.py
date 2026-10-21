"""Chat model for the real runners: LangChain's ChatDatabricks on a Model Serving endpoint.

Authentication comes from the Databricks SDK: the app's service principal on Databricks Apps, or the
CLI profile in DATABRICKS_CONFIG_PROFILE locally. The model is created on first use, so the runtime
starts (and the fake runners work) without any workspace access.
"""

from collections.abc import Callable
from functools import cache

from langchain_core.language_models import BaseChatModel

ModelFactory = Callable[[], BaseChatModel]


def chat_model_factory(endpoint: str, *, temperature: float | None = None) -> ModelFactory:
    """``temperature=None`` leaves it to the endpoint: some models (recent Claude models among them)
    reject the parameter outright, so only set it (LLM_TEMPERATURE) for models that accept it."""

    @cache
    def factory() -> BaseChatModel:
        from databricks_langchain import ChatDatabricks

        model: BaseChatModel = ChatDatabricks(endpoint=endpoint, temperature=temperature)
        return model

    return factory
