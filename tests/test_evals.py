"""Keeps the eval harness working: the dataset is valid and the offline run (fake agent) passes."""

import pytest

from evals.run import evaluate_offline, load_dataset
from evals.scorers import MARKDOWN


def test_dataset_rows_are_contract_requests() -> None:
    rows = load_dataset()
    assert {row["inputs"]["request"]["run_kind"] for row in rows} == {
        "generate",
        "enhance_field",
        "assistant_turn",
    }
    assert all(row["expectations"]["expected_facts"] for row in rows)


@pytest.mark.parametrize(
    "text",
    [
        "Mitigation: run both side by side for two weeks.",
        "The brief's goal says three days - not a week.",
        "Costs 3 * 4 hours; see e.g. the survey_results table.",
    ],
)
def test_plain_prose_is_not_markdown(text: str) -> None:
    assert MARKDOWN.search(text) is None


@pytest.mark.parametrize(
    "text",
    [
        "A **bold** claim",
        "An *emphasised* word",
        "Run `make dev`",
        "# Heading",
        "- item",
        "1. step",
    ],
)
def test_markdown_is_caught(text: str) -> None:
    assert MARKDOWN.search(text) is not None


def test_offline_eval_passes(capsys: pytest.CaptureFixture[str]) -> None:
    assert evaluate_offline(load_dataset()) == 0
    assert "0 failed checks" in capsys.readouterr().out
