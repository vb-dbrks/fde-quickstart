"""The golden record (contracts/agent-api-contract.md) and the Pydantic models must agree.

Every fenced ```json block in the golden record is validated: requests as AgentRunRequest, statuses
as AgentRunStatus, error envelopes as AgentErrorEnvelope. A renamed field, a dropped key or a new
required attribute on either side fails here.
"""

import json
import re
from pathlib import Path
from typing import Any

import pytest

from backend.contracts.agent_contract_v1 import (
    ERROR_CODES,
    STEP_VOCABULARY,
    AgentErrorEnvelope,
    AgentRunRequest,
    AgentRunStatus,
)
from backend.contracts.field_catalog import load_field_catalog
from backend.contracts.validation import check_output, check_request

GOLDEN = Path(__file__).resolve().parents[2] / "contracts" / "agent-api-contract.md"
BLOCK = re.compile(r"```json\n(.*?)```", re.DOTALL)


def examples() -> list[dict[str, Any]]:
    return [json.loads(block) for block in BLOCK.findall(GOLDEN.read_text())]


def requests() -> dict[str, AgentRunRequest]:
    found = [AgentRunRequest.model_validate(e) for e in examples() if "document_context" in e]
    return {request.app_agent_run_id: request for request in found}


def statuses() -> list[AgentRunStatus]:
    return [AgentRunStatus.model_validate(e) for e in examples() if "status" in e]


def test_every_example_is_classified() -> None:
    for example in examples():
        assert "document_context" in example or "status" in example or set(example) == {"error"}


def test_requests_cover_every_run_kind() -> None:
    assert {r.run_kind for r in requests().values()} == set(STEP_VOCABULARY)


def test_statuses_cover_every_state() -> None:
    assert {s.status for s in statuses()} == {"accepted", "running", "succeeded", "failed"}


def test_error_envelopes_validate() -> None:
    envelopes = [AgentErrorEnvelope.model_validate(e) for e in examples() if set(e) == {"error"}]
    assert envelopes
    assert all(envelope.error.code in ERROR_CODES for envelope in envelopes)


def test_step_names_come_from_the_vocabulary() -> None:
    for status in statuses():
        assert [step.name for step in status.step_history] == list(STEP_VOCABULARY[status.run_kind])


@pytest.mark.parametrize("status", [s for s in statuses() if s.status == "succeeded"])
def test_succeeded_examples_follow_the_output_rules(status: AgentRunStatus) -> None:
    catalog = load_field_catalog()
    request = requests()[status.app_agent_run_id]
    assert check_request(request, catalog) == []
    assert status.output is not None
    assert check_output(request, status.output, catalog) == []


def test_failed_examples_name_a_contract_error_code() -> None:
    for status in statuses():
        if status.status == "failed":
            assert status.error is not None
            assert status.error.code in ERROR_CODES
