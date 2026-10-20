"""Offline checks for the eval harness. The evaluation itself needs a workspace: `make eval`."""

from mlflow.entities import Feedback

from evals.run import load_dataset
from evals.scorers import MAX_WORDS, concise


def score_concise(answer: str) -> object:
    feedback = concise(outputs=answer)
    assert isinstance(feedback, Feedback)
    return feedback.value


def test_every_dataset_row_has_inputs_and_expectations() -> None:
    rows = load_dataset()
    assert rows
    for row in rows:
        assert set(row) == {"inputs", "expectations"}
        assert row["inputs"]["message"].strip()
        assert row["expectations"]["expected_facts"]


def test_concise_scorer() -> None:
    assert score_concise("A short answer.") is True
    assert score_concise("word " * (MAX_WORDS + 1)) is False
