"""HTTP surface of the agent runtime: the endpoints of contracts/agent-api-contract.md.

In-process, the app calls this ASGI app directly (httpx ASGITransport). Standalone:

    uvicorn --factory backend.agents.server:create_agent_app --port 9000      (make agent)
"""

import logging
from concurrent.futures import Executor, ThreadPoolExecutor
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from backend.agents.config import AgentSettings
from backend.agents.example_registry import definitions
from backend.agents.fake import FakeAgent
from backend.agents.interaction import InteractionRuntime
from backend.agents.llm import chat_model_factory
from backend.agents.runners import real_runners
from backend.agents.runtime import AgentRuntime, RequestRejected, RunFn
from backend.agents.tracing import RunTracer, enable_mlflow_tracing
from backend.contracts.agent_contract_v1 import (
    AGENT_CONTRACT_VERSION,
    RUN_KINDS,
    AgentError,
    AgentErrorEnvelope,
    AgentRunKind,
    AgentRunRequest,
    FeedbackRequest,
    contract_document,
)
from backend.contracts.execution import ExecutionRequest
from backend.contracts.field_catalog import FieldCatalog, load_field_catalog

logger = logging.getLogger(__name__)


def build_runtime(
    settings: AgentSettings | None = None,
    *,
    executor: Executor | None = None,
    tracer: RunTracer | None = None,
) -> AgentRuntime:
    """Pick fake or real runners per run kind (AGENT_RUNNER / AGENT_RUNNER_OVERRIDES)."""
    settings = settings or AgentSettings()
    registered = definitions(settings)
    settings.check({key: value.example for key, value in registered.items()})
    enabled = {name.strip() for name in settings.enabled_examples.split(",")}
    catalog = load_field_catalog() if "documents" in enabled else FieldCatalog("disabled", {})
    fake = FakeAgent(
        catalog,
        step_seconds=settings.fake_agent_step_seconds,
        fail_at=settings.fake_agent_fail_at,
        version=settings.fake_agent_version,
        drift=settings.fake_agent_drift,
    ).runners()
    choices = settings.runner_choices()
    real: dict[AgentRunKind, RunFn] = {}
    if "real" in choices.values() and "documents" in enabled:
        if not settings.llm_endpoint:
            raise RuntimeError("AGENT_RUNNER=real needs LLM_ENDPOINT (a Model Serving endpoint).")
        real = real_runners(
            chat_model_factory(settings.llm_endpoint, temperature=settings.llm_temperature),
            catalog,
            agent_version=settings.agent_version,
            model_name=settings.llm_endpoint,
        )
    runners = (
        {kind: (real[kind] if choices[kind] == "real" else fake[kind]) for kind in RUN_KINDS}
        if "documents" in enabled
        else {}
    )
    runtime = AgentRuntime(
        runners,
        catalog=catalog,
        executor=executor
        or ThreadPoolExecutor(max_workers=settings.agent_max_workers, thread_name_prefix="agent"),
        tracer=tracer or enable_mlflow_tracing(settings.mlflow_experiment_id),
        runner_names=choices,
        max_runs_kept=settings.agent_max_runs_kept,
    )
    runtime.interactions = InteractionRuntime(
        {k: v for k, v in registered.items() if v.example in enabled},
        runtime.executor,
        traced=bool(settings.mlflow_experiment_id),
        max_runs=settings.agent_max_runs_kept,
    )
    return runtime


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

    @app.get("/agent/v2/definitions")
    async def list_definitions() -> list[dict[str, Any]]:
        return [
            d.descriptor().model_dump(mode="json")
            for d in runtime.interactions.definitions.values()
        ]

    @app.post("/agent/v2/runs")
    async def submit_execution(payload: ExecutionRequest) -> JSONResponse:
        try:
            result = runtime.interactions.submit(payload)
        except ValueError as exc:
            return _error("VALIDATION_ERROR", str(exc), 400)
        return JSONResponse(result.model_dump(mode="json"))

    @app.get("/agent/v2/runs/{run_id}")
    async def poll_execution(run_id: str, after: int = 0) -> JSONResponse:
        result = runtime.interactions.poll(run_id, max(0, after))
        if result is None:
            return _error("RUN_NOT_FOUND", "Run not found", 404)
        return JSONResponse(result.model_dump(mode="json"))

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

    @app.post("/agent/feedback")
    async def record_feedback(request: Request) -> JSONResponse:
        try:
            feedback = FeedbackRequest.model_validate(await request.json())
        except ValidationError as exc:
            return _error("VALIDATION_ERROR", _summarise(exc), status.HTTP_400_BAD_REQUEST)
        except ValueError as exc:
            return _error("VALIDATION_ERROR", str(exc), status.HTTP_400_BAD_REQUEST)
        try:
            # The trace store is called synchronously; keep it off the event loop.
            result = await run_in_threadpool(runtime.record_feedback, feedback)
        except Exception as exc:
            logger.warning("Recording feedback %s failed: %s", feedback.feedback_id, exc)
            if getattr(exc, "error_code", None) == "INVALID_PARAMETER_VALUE":
                # The trace store rejected the feedback itself: sending it again won't help.
                return _error("VALIDATION_ERROR", str(exc), status.HTTP_400_BAD_REQUEST)
            return _error(
                "FEEDBACK_FAILED",
                "The trace store did not accept the feedback.",
                status.HTTP_502_BAD_GATEWAY,
                retryable=True,
            )
        return JSONResponse(result.model_dump(mode="json", exclude_none=True))

    @app.get("/contract")
    async def contract() -> dict[str, Any]:
        return {**contract_document(), "field_catalog_version": runtime._catalog.version}

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {
            "status": "ok",
            "contract_version": AGENT_CONTRACT_VERSION,
            "runners": runtime.runner_names,
        }

    return app
