"""HTTP surface of the agent runtime: the endpoints of contracts/agent-api-contract.md.

In-process, the app calls this ASGI app directly (httpx ASGITransport). Standalone:

    uvicorn --factory backend.agents.server:create_agent_app --port 9000      (make agent)
"""

from concurrent.futures import Executor, ThreadPoolExecutor
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from backend.agents.config import AgentSettings
from backend.agents.fake import FakeAgent
from backend.agents.llm import chat_model_factory
from backend.agents.runners import real_runners
from backend.agents.runtime import AgentRuntime, RequestRejected, RunFn
from backend.agents.tracing import enable_mlflow_tracing
from backend.contracts.agent_contract_v1 import (
    AGENT_CONTRACT_VERSION,
    RUN_KINDS,
    AgentError,
    AgentErrorEnvelope,
    AgentRunKind,
    AgentRunRequest,
    contract_document,
)
from backend.contracts.field_catalog import load_field_catalog


def build_runtime(
    settings: AgentSettings | None = None, *, executor: Executor | None = None
) -> AgentRuntime:
    """Pick fake or real runners per run kind (AGENT_RUNNER / AGENT_RUNNER_OVERRIDES)."""
    settings = settings or AgentSettings()
    settings.check()
    catalog = load_field_catalog()
    fake = FakeAgent(
        catalog,
        step_seconds=settings.fake_agent_step_seconds,
        fail_at=settings.fake_agent_fail_at,
        version=settings.fake_agent_version,
        drift=settings.fake_agent_drift,
    ).runners()
    choices = settings.runner_choices()
    real: dict[AgentRunKind, RunFn] = {}
    if "real" in choices.values():
        if not settings.llm_endpoint:
            raise RuntimeError("AGENT_RUNNER=real needs LLM_ENDPOINT (a Model Serving endpoint).")
        real = real_runners(
            chat_model_factory(settings.llm_endpoint, temperature=settings.llm_temperature),
            catalog,
            agent_version=settings.agent_version,
            model_name=settings.llm_endpoint,
        )
    runners = {kind: (real[kind] if choices[kind] == "real" else fake[kind]) for kind in RUN_KINDS}
    return AgentRuntime(
        runners,
        catalog=catalog,
        executor=executor
        or ThreadPoolExecutor(max_workers=settings.agent_max_workers, thread_name_prefix="agent"),
        tracer=enable_mlflow_tracing(settings.mlflow_experiment_id),
        runner_names=choices,
        max_runs_kept=settings.agent_max_runs_kept,
    )


def _error(code: str, message: str, http_status: int, *, retryable: bool = False) -> JSONResponse:
    envelope = AgentErrorEnvelope(error=AgentError(code=code, message=message, retryable=retryable))
    return JSONResponse(envelope.model_dump(mode="json"), status_code=http_status)


def _summarise(exc: ValidationError) -> str:
    parts = [
        f"{'.'.join(str(p) for p in err['loc']) or '<root>'}: {err['msg']}"
        for err in exc.errors()[:5]
    ]
    return "; ".join(parts)


def create_agent_app(runtime: AgentRuntime | None = None) -> FastAPI:
    runtime = runtime or build_runtime()
    app = FastAPI(
        title="Agent runtime",
        version=AGENT_CONTRACT_VERSION,
        docs_url="/agent/docs",
        openapi_url="/agent/openapi.json",
        redoc_url=None,
    )
    app.state.runtime = runtime

    @app.post("/agent/run")
    async def submit_run(request: Request) -> JSONResponse:
        try:
            run_request = AgentRunRequest.model_validate(await request.json())
            accepted = runtime.submit(run_request)
        except ValidationError as exc:
            return _error("VALIDATION_ERROR", _summarise(exc), status.HTTP_400_BAD_REQUEST)
        except (RequestRejected, ValueError) as exc:
            return _error("VALIDATION_ERROR", str(exc), status.HTTP_400_BAD_REQUEST)
        return JSONResponse(accepted.model_dump(mode="json", exclude_none=True))

    @app.get("/agent/run/{run_id}")
    async def poll_run(run_id: str) -> JSONResponse:
        run = runtime.poll(run_id)
        if run is None:
            return _error(
                "RUN_NOT_FOUND",
                f"Agent run {run_id!r} was not found.",
                status.HTTP_404_NOT_FOUND,
                retryable=True,
            )
        return JSONResponse(run.model_dump(mode="json", exclude_none=True))

    @app.get("/contract")
    async def contract() -> dict[str, Any]:
        return {**contract_document(), "field_catalog_version": load_field_catalog().version}

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {
            "status": "ok",
            "contract_version": AGENT_CONTRACT_VERSION,
            "runners": runtime.runner_names,
        }

    return app
