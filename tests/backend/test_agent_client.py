"""How the app's agent client maps transport and contract failures to typed errors."""

from collections.abc import Callable

import httpx
import pytest

from backend.services.agent_client import (
    USER_AGENT,
    AgentClient,
    AgentContractError,
    AgentRemoteError,
    AgentRunNotFound,
    AgentTimeoutError,
)
from tests.contracts.test_validation import make_request

Handler = Callable[[httpx.Request], httpx.Response]
ACCEPTED = {"app_agent_run_id": "run-1", "run_kind": "generate", "status": "accepted"}


def client_for(handler: Handler, *, retries: int = 3) -> AgentClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://agent.test")
    return AgentClient(http, retries=retries, backoff_seconds=0)


def envelope(status_code: int, code: str, *, retryable: bool) -> httpx.Response:
    return httpx.Response(
        status_code, json={"error": {"code": code, "message": "m", "retryable": retryable}}
    )


async def test_submit_sends_the_contract_version_and_full_request() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(202, json=ACCEPTED)

    status = await client_for(handler).submit(make_request())
    assert status.status == "accepted"
    [request] = seen
    assert (request.method, request.url.path) == ("POST", "/agent/run")
    assert request.headers["User-Agent"] == USER_AGENT
    assert b'"app_agent_run_id":"run-1"' in request.content


async def test_transient_failures_are_retried() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(200, json=ACCEPTED)

    assert (await client_for(handler).poll("run-1")).status == "accepted"
    assert calls == 3


async def test_timeouts_give_up_after_the_retries() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(AgentTimeoutError):
        await client_for(handler, retries=2).poll("run-1")
    assert calls == 2


async def test_an_unreachable_agent_is_a_retryable_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(AgentRemoteError) as excinfo:
        await client_for(handler, retries=1).poll("run-1")
    assert (excinfo.value.code, excinfo.value.retryable) == ("TRANSPORT_ERROR", True)


async def test_an_unknown_run_raises_run_not_found() -> None:
    with pytest.raises(AgentRunNotFound) as excinfo:
        await client_for(returning(envelope(404, "RUN_NOT_FOUND", retryable=True))).poll("run-1")
    assert excinfo.value.status_code == 404


async def test_error_envelopes_keep_their_code_and_retryability() -> None:
    with pytest.raises(AgentRemoteError) as excinfo:
        await client_for(returning(envelope(400, "VALIDATION_ERROR", retryable=False))).submit(
            make_request()
        )
    assert (excinfo.value.code, excinfo.value.retryable) == ("VALIDATION_ERROR", False)
    # A bare 5xx without an envelope still counts as retryable.
    with pytest.raises(AgentRemoteError) as excinfo:
        await client_for(returning(httpx.Response(503, text="upstream down"))).poll("run-1")
    assert (excinfo.value.code, excinfo.value.retryable) == ("HTTP_ERROR", True)


async def test_responses_that_break_the_contract_are_rejected() -> None:
    broken = [
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={**ACCEPTED, "status": "succeeded"}),  # succeeded without output
        httpx.Response(200, json={**ACCEPTED, "unexpected": True}),
    ]
    for response in broken:
        with pytest.raises(AgentContractError):
            await client_for(returning(response)).poll("run-1")


def returning(response: httpx.Response) -> Handler:
    return lambda _: response
