"""Reusable execution engine. No catalog, application services, or persistence imports."""

import logging
import threading
from collections import OrderedDict
from collections.abc import Callable, Mapping
from concurrent.futures import Executor
from dataclasses import dataclass, field
from typing import Any

from ag_ui.core import BaseEvent, Tool
from pydantic import BaseModel

from backend.contracts.execution import AgentDescriptor, ExecutionRequest, ExecutionStatus

logger = logging.getLogger(__name__)


class EventEmitter:
    def __init__(self, publish: Callable[[dict[str, Any]], None]) -> None:
        self._publish = publish

    def emit(self, event: BaseEvent) -> None:
        self._publish(event.model_dump(mode="json", by_alias=True, exclude_none=True))


Runner = Callable[[ExecutionRequest, EventEmitter], BaseModel]


@dataclass(frozen=True)
class AgentDefinition:
    id: str
    example: str
    description: str
    input_model: type[BaseModel]
    result_model: type[BaseModel]
    runner: Runner
    capabilities: tuple[str, ...] = ("state",)
    tools: list[Tool] = field(default_factory=list)

    def descriptor(self) -> AgentDescriptor:
        return AgentDescriptor(
            id=self.id,
            example=self.example,
            description=self.description,
            input_schema=self.input_model.model_json_schema(),
            result_schema=self.result_model.model_json_schema(),
            capabilities=list(self.capabilities),
            tools=self.tools,
        )


class InteractionRuntime:
    def __init__(
        self,
        definitions: Mapping[str, AgentDefinition],
        executor: Executor,
        *,
        traced: bool = False,
        max_runs: int = 1000,
    ) -> None:
        self.definitions = dict(definitions)
        self.executor = executor
        self.traced = traced
        self.max_runs = max_runs
        self._runs: OrderedDict[str, ExecutionStatus] = OrderedDict()
        self._lock = threading.Lock()

    def submit(self, request: ExecutionRequest) -> ExecutionStatus:
        definition = self.definitions.get(request.agent_id)
        if definition is None:
            raise ValueError(f"Unknown agent: {request.agent_id}")
        definition.input_model.model_validate(request.input)
        with self._lock:
            if request.run_id in self._runs:
                return self._runs[request.run_id].model_copy(deep=True)
            self._runs[request.run_id] = ExecutionStatus(run_id=request.run_id, status="accepted")
            for key in list(self._runs):
                if len(self._runs) <= self.max_runs:
                    break
                if self._runs[key].status in ("succeeded", "failed"):
                    del self._runs[key]
        self.executor.submit(self._execute, request, definition)
        return self.poll(request.run_id, 0) or ExecutionStatus(
            run_id=request.run_id, status="accepted"
        )

    def poll(self, run_id: str, after: int) -> ExecutionStatus | None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return None
            result = run.model_copy(deep=True)
            result.events = result.events[after:]
            return result

    def _execute(self, request: ExecutionRequest, definition: AgentDefinition) -> None:
        def publish(event: dict[str, Any]) -> None:
            with self._lock:
                run = self._runs[request.run_id]
                run.events.append(event)
                run.cursor = len(run.events)

        def invoke() -> dict[str, Any]:
            output = definition.runner(request, EventEmitter(publish))
            return definition.result_model.model_validate(output.model_dump()).model_dump(
                mode="json"
            )

        with self._lock:
            self._runs[request.run_id].status = "running"
        try:
            trace_id = None
            if self.traced:
                import mlflow

                with mlflow.start_span(name=f"agent.{request.agent_id}", span_type="AGENT") as span:
                    span.set_inputs(request.model_dump(mode="json"))
                    mlflow.update_current_trace(
                        user=request.initiator,
                        session_id=request.thread_id,
                        tags={"app_agent_run_id": request.run_id, "agent_id": request.agent_id},
                    )
                    result = invoke()
                    span.set_outputs(result)
                    trace_id = span.trace_id
            else:
                result = invoke()
            with self._lock:
                run = self._runs[request.run_id]
                run.result, run.trace_id, run.status = result, trace_id, "succeeded"
        except Exception:
            logger.exception("Agent %s failed", request.run_id)
            with self._lock:
                run = self._runs[request.run_id]
                run.status, run.error = "failed", "The agent could not produce a valid result."
