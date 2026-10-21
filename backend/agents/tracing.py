"""One MLflow trace per agent run; LangChain calls made during the run nest under it (autolog)."""

import logging
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Any, Protocol

from backend.contracts.agent_contract_v1 import AgentRunRequest

logger = logging.getLogger(__name__)


class TraceHandle:
    def __init__(self, span: Any = None) -> None:
        self._span = span

    @property
    def trace_id(self) -> str | None:
        return getattr(self._span, "trace_id", None) if self._span is not None else None

    def record_output(self, output: dict[str, Any]) -> None:
        if self._span is not None:
            self._span.set_outputs(output)


class RunTracer(Protocol):
    def trace(self, request: AgentRunRequest) -> AbstractContextManager[TraceHandle]: ...


class NoopTracer:
    @contextmanager
    def trace(self, request: AgentRunRequest) -> Iterator[TraceHandle]:
        yield TraceHandle()


class MlflowTracer:
    """Root span per run, tagged with the app's run id so traces and ``agent_runs`` rows link up."""

    @contextmanager
    def trace(self, request: AgentRunRequest) -> Iterator[TraceHandle]:
        import mlflow

        with mlflow.start_span(name=f"agent.{request.run_kind}", span_type="AGENT") as span:
            span.set_inputs(request.model_dump(mode="json"))
            span.set_attributes(
                {
                    "app_agent_run_id": request.app_agent_run_id,
                    "document_type": request.document_context.document_type,
                    "run_kind": request.run_kind,
                }
            )
            yield TraceHandle(span)


def enable_mlflow_tracing(experiment_id: str | None) -> RunTracer:
    """Send traces to ``experiment_id`` and autolog LangChain; without one, tracing is off."""
    if not experiment_id:
        return NoopTracer()
    try:
        import mlflow

        mlflow.set_tracking_uri("databricks")
        mlflow.set_experiment(experiment_id=experiment_id)
        mlflow.langchain.autolog()
    except Exception:
        logger.warning("MLflow tracing could not be enabled; continuing without it", exc_info=True)
        return NoopTracer()
    return MlflowTracer()
