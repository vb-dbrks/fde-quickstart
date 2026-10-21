"""Accepts agent runs, executes them in the background and keeps their status until polled.

Stateless by design (ADR 0004): the only state is this process-local registry of in-flight and
recently finished runs, keyed by the app's ``app_agent_run_id``. It holds no business data, and losing
it (a restart) only means the app sees RUN_NOT_FOUND and fails the run as retryable.
"""

import logging
import threading
from collections import OrderedDict
from collections.abc import Callable, Iterator, Mapping
from concurrent.futures import Executor, Future
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, ParamSpec, TypeVar

from backend.agents.tracing import NoopTracer, RunTracer, TraceHandle
from backend.contracts.agent_contract_v1 import (
    STEP_VOCABULARY,
    AgentError,
    AgentOutput,
    AgentRunKind,
    AgentRunRequest,
    AgentRunStatus,
    AgentStep,
)
from backend.contracts.field_catalog import FieldCatalog
from backend.contracts.validation import check_output, check_request

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


class InlineExecutor(Executor):
    """Runs submitted work in the calling thread, so a run has finished when ``submit`` returns.

    For evals (model calls trace under the evaluation's trace) and tests (deterministic runs).
    """

    def submit(self, fn: Callable[P, T], /, *args: P.args, **kwargs: P.kwargs) -> Future[T]:
        future: Future[T] = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as exc:
            future.set_exception(exc)
        return future


class AgentRunFailed(Exception):
    """Raised by runners for failures they understand; becomes a ``failed`` status."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class RequestRejected(Exception):
    """The request breaks a catalog rule; the server answers 400 VALIDATION_ERROR."""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class Steps:
    """Progress through a run kind's step vocabulary, reported to the poller as it happens."""

    def __init__(self, names: tuple[str, ...], on_change: Callable[[list[AgentStep]], None]):
        self._steps = [AgentStep(name=name, status="pending") for name in names]
        self._on_change = on_change

    @property
    def history(self) -> list[AgentStep]:
        return list(self._steps)

    def _replace(self, name: str, **changes: Any) -> None:
        for index, step in enumerate(self._steps):
            if step.name == name:
                self._steps[index] = step.model_copy(update=changes)
                self._on_change(self.history)
                return
        raise ValueError(f"unknown step {name!r}")

    @contextmanager
    def step(self, name: str) -> Iterator[None]:
        self._replace(name, status="running", started_at=_now())
        try:
            yield
        except BaseException:
            self._replace(name, status="failed", completed_at=_now())
            raise
        self._replace(name, status="completed", completed_at=_now())


RunFn = Callable[[AgentRunRequest, Steps], AgentOutput]


class AgentRuntime:
    def __init__(
        self,
        runners: Mapping[AgentRunKind, RunFn],
        *,
        catalog: FieldCatalog,
        executor: Executor,
        tracer: RunTracer | None = None,
        runner_names: Mapping[str, str] | None = None,
        max_runs_kept: int = 1000,
    ) -> None:
        self._runners = dict(runners)
        self._catalog = catalog
        self._executor = executor
        self._tracer = tracer or NoopTracer()
        self._runner_names = dict(runner_names or {})
        self._max_runs_kept = max_runs_kept
        self._runs: OrderedDict[str, AgentRunStatus] = OrderedDict()
        self._lock = threading.Lock()

    @property
    def runner_names(self) -> dict[str, str]:
        return dict(self._runner_names)

    def submit(self, request: AgentRunRequest) -> AgentRunStatus:
        """Accept ``request`` and start it. Re-submitting a known run id returns that run."""
        problems = check_request(request, self._catalog)
        if problems:
            raise RequestRejected("; ".join(problems))
        run_id = request.app_agent_run_id
        with self._lock:
            existing = self._runs.get(run_id)
            if existing is not None:
                return existing
            accepted = AgentRunStatus(
                app_agent_run_id=run_id,
                run_kind=request.run_kind,
                status="accepted",
                step_history=[
                    AgentStep(name=name, status="pending")
                    for name in STEP_VOCABULARY[request.run_kind]
                ],
            )
            self._runs[run_id] = accepted
            self._evict()
        self._executor.submit(self._execute, request)
        return accepted

    def poll(self, run_id: str) -> AgentRunStatus | None:
        with self._lock:
            return self._runs.get(run_id)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _update(self, run_id: str, **changes: Any) -> None:
        with self._lock:
            current = self._runs.get(run_id)
            if current is not None:
                self._runs[run_id] = current.model_copy(update=changes)

    def _evict(self) -> None:
        excess = len(self._runs) - self._max_runs_kept
        if excess <= 0:
            return
        terminal = [rid for rid, run in self._runs.items() if run.status in ("succeeded", "failed")]
        for run_id in terminal[:excess]:
            del self._runs[run_id]

    def _execute(self, request: AgentRunRequest) -> None:
        run_id = request.app_agent_run_id
        self._update(run_id, status="running")
        steps = Steps(
            STEP_VOCABULARY[request.run_kind],
            on_change=lambda history: self._update(run_id, step_history=history),
        )
        handle = TraceHandle()
        try:
            with self._tracer.trace(request) as handle:
                output = self._runners[request.run_kind](request, steps)
                problems = check_output(request, output, self._catalog)
                if problems:
                    raise AgentRunFailed("OUTPUT_INVALID", "; ".join(problems))
                handle.record_output(output.model_dump(mode="json"))
        except AgentRunFailed as exc:
            logger.warning("Agent run %s failed: %s %s", run_id, exc.code, exc.message)
            self._finish(
                run_id,
                steps,
                handle,
                error=AgentError(code=exc.code, message=exc.message, retryable=exc.retryable),
            )
            return
        except Exception:
            logger.exception("Agent run %s crashed", run_id)
            self._finish(
                run_id,
                steps,
                handle,
                error=AgentError(
                    code="INTERNAL_ERROR", message="The agent failed unexpectedly.", retryable=True
                ),
            )
            return
        self._finish(run_id, steps, handle, output=output)

    def _finish(
        self,
        run_id: str,
        steps: Steps,
        handle: TraceHandle,
        *,
        output: AgentOutput | None = None,
        error: AgentError | None = None,
    ) -> None:
        self._update(
            run_id,
            status="succeeded" if error is None else "failed",
            step_history=steps.history,
            output=output,
            error=error,
            trace_id=handle.trace_id,
        )
