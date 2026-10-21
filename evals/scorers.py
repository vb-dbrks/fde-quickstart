"""Deterministic scorers. They need no model, so `make eval DEV=1` runs them offline against the fake
agent; `make eval` adds the built-in LLM judges (evals/run.py).

``outputs`` is what ``predict`` in evals/run.py returns: the run's final contract status as a dict.
"""

import re
from typing import Any

from mlflow.entities import Feedback
from mlflow.genai.scorers import scorer

from backend.contracts.agent_contract_v1 import AgentRunRequest
from backend.contracts.field_catalog import load_field_catalog
from backend.contracts.validation import requested_fields

# Chat replies are read in a narrow panel.
MAX_ANSWER_WORDS = 120
# Markdown the app would show literally: emphasis, code, headings, list markers at a line start.
MARKDOWN = re.compile(
    r"\*\*|__|`|(?<![\w*])\*(?=\S)[^*\n]+(?<=\S)\*(?![\w*])"
    r"|^\s{0,3}#{1,6}\s|^\s*[-*+]\s|^\s*\d+[.)]\s",
    re.MULTILINE,
)


def _request(inputs: dict[str, Any]) -> AgentRunRequest:
    return AgentRunRequest.model_validate(inputs["request"])


def _output(outputs: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = outputs.get("output") or {}
    return output


@scorer
def follows_contract(outputs: dict[str, Any]) -> Feedback:
    """The run succeeded. The runtime fails runs whose output breaks the contract (OUTPUT_INVALID)."""
    if outputs.get("status") == "succeeded":
        return Feedback(value=True, rationale="succeeded")
    error = outputs.get("error") or {}
    return Feedback(value=False, rationale=f"{error.get('code')}: {error.get('message')}")


@scorer
def fields_complete(inputs: dict[str, Any], outputs: dict[str, Any]) -> Feedback:
    """Every field the request asked for came back with a value (assistant turns: an answer)."""
    request = _request(inputs)
    output = _output(outputs)
    if request.run_kind == "assistant_turn":
        answer = (output.get("answer") or {}).get("content", "")
        return Feedback(
            value=bool(answer.strip()), rationale="answer present" if answer else "no answer"
        )
    returned = {f["field_path"]: f["value"] for f in output.get("fields", [])}
    missing = [
        path for path in requested_fields(request, load_field_catalog()) if not returned.get(path)
    ]
    return Feedback(
        value=not missing, rationale=f"missing: {missing}" if missing else "all present"
    )


@scorer
def cites_sources(inputs: dict[str, Any], outputs: dict[str, Any]) -> Feedback | None:
    """With source documents provided, the output cites at least one of them."""
    request = _request(inputs)
    if not request.source_documents:
        return None  # not applicable
    output = _output(outputs)
    citations = [c for f in output.get("fields", []) for c in f.get("citations", [])]
    citations += (output.get("answer") or {}).get("citations", [])
    return Feedback(value=bool(citations), rationale=f"{len(citations)} citations")


@scorer
def concise(inputs: dict[str, Any], outputs: dict[str, Any]) -> Feedback | None:
    """Chat answers stay short enough to read in the app."""
    if _request(inputs).run_kind != "assistant_turn":
        return None
    answer = (_output(outputs).get("answer") or {}).get("content", "")
    words = len(answer.split())
    return Feedback(
        value=words <= MAX_ANSWER_WORDS, rationale=f"{words} words (limit {MAX_ANSWER_WORDS})"
    )


@scorer
def plain_text(outputs: dict[str, Any]) -> Feedback | None:
    """Field values and answers contain no Markdown: the app shows them as plain text.

    Deterministic on purpose - LLM judges flag ordinary punctuation and JSON arrays as Markdown.
    """
    output = _output(outputs)
    texts: list[str] = []
    for field in output.get("fields", []):
        value = field.get("value")
        texts.extend(value if isinstance(value, list) else [str(value)])
    if answer := (output.get("answer") or {}).get("content"):
        texts.append(answer)
    if not texts:
        return None  # the run failed; follows_contract reports it
    flagged = next((text for text in texts if MARKDOWN.search(text)), None)
    if flagged is None:
        return Feedback(value=True, rationale="no Markdown")
    return Feedback(value=False, rationale=f"Markdown in {flagged[:80]!r}")


DETERMINISTIC = [follows_contract, fields_complete, cites_sources, concise, plain_text]
