"""One MLflow trace per agent run, and users' feedback stored on it.

LangChain calls made during a run nest under the run's root span (autolog). Each trace records the
user who started the run and a session - the conversation for chat turns, the document otherwise -
so the Databricks UI can group and filter by them. Feedback the app sends later (POST /agent/feedback)
is stored on the same trace as assessments with a HUMAN source.
"""

import logging
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Any, Protocol

from backend.contracts.agent_contract_v1 import AgentRunRequest, FeedbackRequest

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

    def record_feedback(self, feedback: FeedbackRequest) -> str | None:
        """Store the feedback on its trace; return the assessment id, or None if tracing is off."""
        ...


class NoopTracer:
    @contextmanager
    def trace(self, request: AgentRunRequest) -> Iterator[TraceHandle]:
        yield TraceHandle()

    def record_feedback(self, feedback: FeedbackRequest) -> str | None:
        return None


def trace_session(request: AgentRunRequest) -> str:
    """The trace's session: the conversation for chat turns, the document for everything else."""
    if request.assistant_context is not None:
        return f"thread:{request.assistant_context.thread_id}"
    return f"document:{request.document_context.document_id}"


class _MlflowTraceHandle(TraceHandle):
    def record_output(self, output: dict[str, Any]) -> None:
        import mlflow

        super().record_output(output)
        meta = output.get("meta") or {}
        keys = ("runner", "agent_version", "model", "prompt_version")
        mlflow.update_current_trace(tags={k: str(meta[k]) for k in keys if meta.get(k) is not None})


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
            mlflow.update_current_trace(
                user=request.meta.initiator,
                session_id=trace_session(request),
                tags={
                    "app_agent_run_id": request.app_agent_run_id,
                    "run_kind": request.run_kind,
                    "document_type": request.document_context.document_type,
                    "document_id": request.document_context.document_id,
                },
            )
            yield _MlflowTraceHandle(span)

    def record_feedback(self, feedback: FeedbackRequest) -> str | None:
        import mlflow
        from mlflow.entities import AssessmentSource, AssessmentSourceType

        if (existing := _recorded_already(feedback)) is not None:
            return existing  # a retry of feedback that was stored before the app heard back
        source = AssessmentSource(source_type=AssessmentSourceType.HUMAN, source_id=feedback.user)
        metadata = {**feedback.metadata, "feedback_id": feedback.feedback_id}
        if feedback.kind == "expectation":
            if (
                feedback.replaces
            ):  # the user corrected the field again: the latest value is the truth
                _delete_quietly(feedback.trace_id, feedback.replaces)
            assessment = mlflow.log_expectation(
                trace_id=feedback.trace_id,
                name=feedback.name,
                value=feedback.value,
                source=source,
                metadata=metadata,
            )
        elif feedback.replaces:  # the user changed their mind: keep the old one, marked invalid
            assessment = mlflow.override_feedback(
                trace_id=feedback.trace_id,
                assessment_id=feedback.replaces,
                value=feedback.value,
                rationale=feedback.rationale,
                source=source,
                metadata=metadata,
            )
        else:
            assessment = mlflow.log_feedback(
                trace_id=feedback.trace_id,
                name=feedback.name,
                value=feedback.value,
                rationale=feedback.rationale,
                source=source,
                metadata=metadata,
            )
        _tag_feedback(feedback)
        assessment_id: str | None = assessment.assessment_id
        return assessment_id


# Trace tags that make traces with feedback searchable: Databricks' trace search filters on tags,
# not on assessments (e.g. `tags.has_negative_feedback = 'true'`). Tags only ever get set.
FEEDBACK_TAGS = ("has_feedback", "has_negative_feedback", "has_correction")


def _tag_feedback(feedback: FeedbackRequest) -> None:
    import mlflow

    tags = ["has_feedback"]
    if feedback.kind == "expectation":
        tags.append("has_correction")
    elif feedback.value is False:
        tags.append("has_negative_feedback")
    for tag in tags:
        mlflow.set_trace_tag(feedback.trace_id, tag, "true")


def _recorded_already(feedback: FeedbackRequest) -> str | None:
    import mlflow

    trace = mlflow.get_trace(feedback.trace_id)
    if trace is None:
        # MLflow uploads traces in the background: feedback on a run that only just finished can
        # arrive first. Finish this process's uploads, then look again.
        mlflow.flush_trace_async_logging()
        trace = mlflow.get_trace(feedback.trace_id)
    for assessment in trace.info.assessments if trace is not None else []:
        if (assessment.metadata or {}).get("feedback_id") == feedback.feedback_id:
            found: str = assessment.assessment_id
            return found
    return None


def _delete_quietly(trace_id: str, assessment_id: str) -> None:
    import mlflow

    try:
        mlflow.delete_assessment(trace_id=trace_id, assessment_id=assessment_id)
    except Exception:
        logger.info("Assessment %s on %s was already gone", assessment_id, trace_id)


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
