"""MlflowTracer against a real (local, SQLite) MLflow store: trace context and users' feedback."""

from collections.abc import Iterator
from pathlib import Path

import mlflow
import pytest

from backend.agents.tracing import MlflowTracer
from backend.contracts.agent_contract_v1 import FeedbackRequest
from evals.from_feedback import rows_from_traces
from tests.contracts.test_validation import make_request


@pytest.fixture(scope="module")
def tracer(tmp_path_factory: pytest.TempPathFactory) -> Iterator[MlflowTracer]:
    root: Path = tmp_path_factory.mktemp("mlflow")  # one store for the module: creating it is slow
    previous = mlflow.get_tracking_uri()
    mlflow.set_tracking_uri(f"sqlite:///{root / 'mlflow.db'}")
    # Artifacts (trace data) in the temp dir too, not ./mlruns in the repo.
    experiment_id = mlflow.create_experiment("feedback-test", artifact_location=root.as_uri())
    mlflow.set_experiment(experiment_id=experiment_id)
    yield MlflowTracer()
    mlflow.set_tracking_uri(previous)


def traced_run(tracer: MlflowTracer) -> str:
    with tracer.trace(make_request("assistant_turn")) as handle:
        handle.record_output(
            {"answer": {"content": "Hi"}, "meta": {"runner": "real", "model": "m"}}
        )
    assert handle.trace_id is not None
    mlflow.flush_trace_async_logging()  # traces are exported in the background
    return handle.trace_id


def feedback(trace_id: str, **changes: object) -> FeedbackRequest:
    fields: dict[str, object] = {
        "feedback_id": "fb-1",
        "trace_id": trace_id,
        "kind": "feedback",
        "name": "answer_rating",
        "value": False,
        "rationale": "Missed the point.",
        "user": "editor@example.com",
        "metadata": {"message_id": "7"},
    }
    return FeedbackRequest.model_validate({**fields, **changes})


def test_traces_record_the_user_session_and_run(tracer: MlflowTracer) -> None:
    trace = mlflow.get_trace(traced_run(tracer))
    assert trace is not None
    assert trace.info.trace_metadata["mlflow.trace.user"] == "a@example.com"
    assert trace.info.trace_metadata["mlflow.trace.session"] == "thread:t"
    assert trace.info.tags["app_agent_run_id"] == "run-1"
    assert (trace.info.tags["run_kind"], trace.info.tags["runner"]) == ("assistant_turn", "real")


def test_feedback_is_stored_once_with_its_user(tracer: MlflowTracer) -> None:
    trace_id = traced_run(tracer)
    first = tracer.record_feedback(feedback(trace_id))
    assert first is not None
    assert tracer.record_feedback(feedback(trace_id)) == first  # a retry stores nothing new

    trace = mlflow.get_trace(trace_id)
    assert trace is not None
    [stored] = trace.info.assessments
    assert (stored.name, stored.feedback.value, stored.rationale) == (
        "answer_rating",
        False,
        "Missed the point.",
    )
    assert (stored.source.source_type, stored.source.source_id) == ("HUMAN", "editor@example.com")
    assert stored.metadata["message_id"] == "7"


def test_a_changed_rating_overrides_the_old_one(tracer: MlflowTracer) -> None:
    trace_id = traced_run(tracer)
    first = tracer.record_feedback(feedback(trace_id))
    second = tracer.record_feedback(
        feedback(trace_id, feedback_id="fb-2", value=True, rationale=None, replaces=first)
    )
    trace = mlflow.get_trace(trace_id)
    assert trace is not None
    by_id = {a.assessment_id: a for a in trace.info.assessments}
    assert by_id[second].feedback.value is True
    assert by_id[first].valid is False  # kept for the record, no longer counted


def test_a_new_correction_replaces_the_old_one(tracer: MlflowTracer) -> None:
    trace_id = traced_run(tracer)
    old = tracer.record_feedback(
        feedback(trace_id, kind="expectation", name="brief__summary", value="First fix")
    )
    tracer.record_feedback(
        feedback(
            trace_id,
            feedback_id="fb-2",
            kind="expectation",
            name="brief__summary",
            value="Better fix",
            replaces=old,
        )
    )
    trace = mlflow.get_trace(trace_id)
    assert trace is not None
    assert [(a.name, a.expectation.value) for a in trace.info.assessments] == [
        ("brief__summary", "Better fix")
    ]


def test_feedback_becomes_evaluation_rows(tracer: MlflowTracer) -> None:
    """evals/from_feedback.py: a corrected, rated run becomes a replayable row with expected facts."""
    request = make_request()
    with tracer.trace(request) as handle:
        handle.record_output({"fields": [], "meta": {"runner": "real"}})
    mlflow.flush_trace_async_logging()
    assert handle.trace_id is not None
    trace_id = handle.trace_id
    tracer.record_feedback(
        feedback(
            trace_id,
            feedback_id="r",
            name="field_rating",
            metadata={"field_path": "brief.risks", "reasons": "missing_detail"},
        )
    )
    tracer.record_feedback(
        feedback(
            trace_id,
            feedback_id="c",
            kind="expectation",
            name="brief__risks",
            value=["Scope creep", "Data access"],
            metadata={"field_path": "brief.risks"},
        )
    )
    unrated = traced_run(tracer)

    traces = mlflow.search_traces(  # the filter from_feedback.py uses
        filter_string="tags.has_feedback = 'true'", return_type="list", max_results=100
    )
    tagged = mlflow.get_trace(trace_id)
    assert tagged is not None
    assert {k: v for k, v in tagged.info.tags.items() if k.startswith("has_")} == {
        "has_feedback": "true",
        "has_negative_feedback": "true",
        "has_correction": "true",
    }
    rows = {row["trace_id"]: row for row in rows_from_traces(traces)}
    assert unrated not in rows  # only traces people gave feedback on
    row = rows[trace_id]
    assert row["inputs"]["request"] == request.model_dump(mode="json")
    assert row["expectations"] == {"expected_facts": ["brief.risks: Scope creep; Data access"]}
    assert row["feedback"] == [
        {
            "name": "field_rating",
            "value": False,
            "comment": "Missed the point.",
            "user": "editor@example.com",
            "field_path": "brief.risks",
            "reasons": "missing_detail",
        }
    ]
