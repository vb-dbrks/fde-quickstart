"""OpenAI-compatible client for Databricks Model Serving (Foundation Model APIs or custom endpoints)."""

import json
from collections.abc import Generator
from typing import Any

import httpx2
from databricks.sdk.core import Config
from openai import AsyncOpenAI

# Stay under the Databricks Apps proxy's 120 s request limit.
REQUEST_TIMEOUT = httpx2.Timeout(90.0, connect=10.0)
# Headers that no longer describe the body once it has been decoded and rewritten.
_STALE_HEADERS = {"content-length", "content-encoding", "transfer-encoding"}


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


def flatten_message_content(completion: dict[str, Any]) -> bool:
    """Turn list-valued ``message.content`` into a string. Returns True if anything changed.

    Some Databricks-hosted models (e.g. Claude with reasoning) return content as a list of parts,
    such as ``[{"type": "reasoning", ...}, {"type": "text", "text": "..."}]``. The OpenAI Agents
    SDK only accepts a string, so keep the text parts and drop the rest.
    """
    changed = False
    for choice in completion.get("choices") or []:
        message = choice.get("message") or {}
        content = message.get("content")
        if isinstance(content, list):
            text = "".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            )
            message["content"] = text or None
            changed = True
    return changed


class ChatCompletionsCompat(httpx2.AsyncBaseTransport):
    """Rewrites chat-completions responses with :func:`flatten_message_content`."""

    def __init__(self, inner: httpx2.AsyncBaseTransport) -> None:
        self._inner = inner

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        response = await self._inner.handle_async_request(request)
        is_json = "application/json" in response.headers.get("content-type", "")
        if not (request.url.path.endswith("/chat/completions") and is_json):
            return response
        await response.aread()
        completion = json.loads(response.content)
        if not isinstance(completion, dict) or not flatten_message_content(completion):
            return response
        headers = {k: v for k, v in response.headers.items() if k.lower() not in _STALE_HEADERS}
        return httpx2.Response(
            response.status_code,
            headers=headers,
            content=json.dumps(completion).encode(),
            request=request,
        )

    async def aclose(self) -> None:
        await self._inner.aclose()


def databricks_openai_client(
    config: Config | None = None, *, transport: httpx2.AsyncBaseTransport | None = None
) -> AsyncOpenAI:
    """``transport`` is for tests (e.g. ``httpx2.MockTransport``)."""
    config = config or Config()
    http_client = httpx2.AsyncClient(
        auth=DatabricksAuth(config),
        timeout=REQUEST_TIMEOUT,
        transport=ChatCompletionsCompat(transport or httpx2.AsyncHTTPTransport()),
    )
    return AsyncOpenAI(
        base_url=f"{config.host}/serving-endpoints",
        api_key="unused",  # DatabricksAuth sets the Authorization header
        http_client=http_client,
    )
