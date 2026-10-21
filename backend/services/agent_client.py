"""Typed client for the agent contract (contracts/agent-api-contract.md).

Stateless: every submit carries the full context (ADR 0004). Async + poll: submit returns at once
with ``accepted``; the caller polls until ``succeeded`` or ``failed`` (ADR 0003).

Two transports, one wire format:

* in-process (default) - ``httpx.ASGITransport`` straight into the agent runtime's ASGI app, so a
  single-app deployment still goes through JSON serialisation and contract validation;
* HTTP - an agent deployed elsewhere (its own Databricks App, or `make agent`), called with the app's
  Databricks OAuth token.

Failures surface as distinct exceptions: AgentTimeoutError (gave up after retries),
AgentRunNotFound (the agent doesn't know the run - usually it restarted), AgentRemoteError (the agent
returned an error envelope) and AgentContractError (the response broke the contract).
"""

import asyncio
import logging
from collections.abc import Generator
from typing import Any

import httpx
from pydantic import ValidationError
from starlette.types import ASGIApp

from backend.contracts.agent_contract_v1 import (
    AGENT_CONTRACT_VERSION,
    AgentRunRequest,
    AgentRunStatus,
)

logger = logging.getLogger(__name__)

USER_AGENT = f"quickstart-app agent-contract/{AGENT_CONTRACT_VERSION}"
_IN_PROCESS_BASE = "http://agent.internal"


class AgentClientError(Exception):
    """Base class for errors from the agent client."""


class AgentTimeoutError(AgentClientError):
    """The agent did not answer in time after the configured retries."""


class AgentRemoteError(AgentClientError):
    def __init__(self, status_code: int, code: str, message: str, *, retryable: bool = False):
        super().__init__(f"agent {status_code} {code}: {message}")
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retryable = retryable


class AgentRunNotFound(AgentRemoteError):
    """The agent has no record of the run (RUN_NOT_FOUND)."""


class AgentContractError(AgentClientError):
    def __init__(self, message: str, *, raw: Any = None) -> None:
        super().__init__(message)
        self.raw = raw


def _is_local(base_url: str) -> bool:
    return httpx.URL(base_url).host in {"localhost", "127.0.0.1", "::1"}


class DatabricksAuth(httpx.Auth):
    """Adds a current Databricks token (the app's service principal on Databricks Apps)."""

    def __init__(self) -> None:
        from databricks.sdk.core import Config

        self._config = Config()

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response]:
        request.headers.update(self._config.authenticate())
        yield request


class AgentClient:
    def __init__(
        self, http: httpx.AsyncClient, *, retries: int = 3, backoff_seconds: float = 0.5
    ) -> None:
        self._http = http
        self._retries = max(1, retries)
        self._backoff = backoff_seconds

    @classmethod
    def in_process(cls, agent_app: ASGIApp, *, timeout: float) -> "AgentClient":
        transport = httpx.ASGITransport(app=agent_app)
        http = httpx.AsyncClient(transport=transport, base_url=_IN_PROCESS_BASE, timeout=timeout)
        return cls(http, retries=1)

    @classmethod
    def over_http(
        cls, base_url: str, *, timeout: float, auth: httpx.Auth | None = None
    ) -> "AgentClient":
        """An agent at ``base_url``. Unless ``auth`` is given, requests carry the app's Databricks
        token - except to a local agent (`make agent`), which needs none."""
        if auth is None:
            auth = httpx.Auth() if _is_local(base_url) else DatabricksAuth()
        http = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout, auth=auth)
        return cls(http)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def submit(self, request: AgentRunRequest) -> AgentRunStatus:
        body = request.model_dump(mode="json", exclude_none=True)
        return self._status(await self._request("POST", "/agent/run", json=body))

    async def poll(self, run_id: str) -> AgentRunStatus:
        return self._status(await self._request("GET", f"/agent/run/{run_id}"))

    async def contract(self) -> dict[str, Any]:
        data: dict[str, Any] = (await self._request("GET", "/contract")).json()
        return data

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        for attempt in range(1, self._retries + 1):
            try:
                response = await self._http.request(
                    method, path, headers={"User-Agent": USER_AGENT}, **kwargs
                )
            except httpx.TimeoutException as exc:
                if attempt == self._retries:
                    raise AgentTimeoutError(f"agent {method} {path} timed out") from exc
            except httpx.HTTPError as exc:
                if attempt == self._retries:
                    raise AgentRemoteError(0, "TRANSPORT_ERROR", str(exc), retryable=True) from exc
            else:
                self._raise_for_error(response)
                return response
            logger.warning("agent %s %s failed (attempt %d), retrying", method, path, attempt)
            await asyncio.sleep(self._backoff * 2 ** (attempt - 1))
        raise AgentClientError("unreachable")  # pragma: no cover

    @staticmethod
    def _raise_for_error(response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        # The contract's envelope is {"error": {"code", "message", "retryable"}}; anything in front of
        # the agent (a proxy, the sign-in layer) may answer with other shapes, which are not envelopes.
        try:
            body = response.json()
        except ValueError:
            body = None
        error = body.get("error") if isinstance(body, dict) else None
        if not isinstance(error, dict):
            error = {}
        code = str(error.get("code") or "HTTP_ERROR")
        message = str(error.get("message") or response.text or response.reason_phrase)
        retryable = bool(error.get("retryable", response.status_code >= 500))
        error_type = AgentRunNotFound if code == "RUN_NOT_FOUND" else AgentRemoteError
        raise error_type(response.status_code, code, message, retryable=retryable)

    @staticmethod
    def _status(response: httpx.Response) -> AgentRunStatus:
        try:
            return AgentRunStatus.model_validate(response.json())
        except ValueError as exc:
            if isinstance(exc, ValidationError):
                logger.error("agent response broke the contract: %s", exc)
            raise AgentContractError(
                "agent response did not match contract v1", raw=response.text[:2000]
            ) from exc
