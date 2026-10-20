"""OpenAI-compatible client for Databricks Model Serving (Foundation Model APIs or custom endpoints)."""

from collections.abc import Generator

import httpx2
from databricks.sdk.core import Config
from openai import AsyncOpenAI

# Stay under the Databricks Apps proxy's 120 s request limit.
REQUEST_TIMEOUT = httpx2.Timeout(90.0, connect=10.0)


class DatabricksAuth(httpx2.Auth):
    """Adds a current Databricks token to every request.

    The SDK caches and refreshes the token, so this works with the app's service principal on
    Databricks Apps and with a CLI profile (DATABRICKS_CONFIG_PROFILE) locally.
    """

    def __init__(self, config: Config) -> None:
        self._config = config

    def auth_flow(self, request: httpx2.Request) -> Generator[httpx2.Request, httpx2.Response]:
        request.headers.update(self._config.authenticate())
        yield request


def databricks_openai_client(
    config: Config | None = None, *, transport: httpx2.AsyncBaseTransport | None = None
) -> AsyncOpenAI:
    """``transport`` is for tests (e.g. ``httpx2.MockTransport``)."""
    config = config or Config()
    http_client = httpx2.AsyncClient(
        auth=DatabricksAuth(config), timeout=REQUEST_TIMEOUT, transport=transport
    )
    return AsyncOpenAI(
        base_url=f"{config.host}/serving-endpoints",
        api_key="unused",  # DatabricksAuth sets the Authorization header
        http_client=http_client,
    )
