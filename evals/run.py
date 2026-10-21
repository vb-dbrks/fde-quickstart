"""Evaluate the agent with MLflow 3.

    make eval DEV=1                                      # offline: fake agent, deterministic scorers
    make eval PROFILE=<cli-profile> LLM_ENDPOINT=<name>  # real agent + LLM judges, logged to MLflow

Each row of dataset.jsonl holds a contract request (contracts/agent-api-contract.md) and the facts a
good result contains. Rows run through the same AgentRuntime the app uses - request checks, steps,
output checks - so an eval measures what users get. To turn a real run into a test case, copy its
``request_payload`` from the app's agent_runs table into a new row. Scorers live in scorers.py.

The real run calls the model endpoint in your CLI profile's workspace and logs to an MLflow
experiment there (default /Users/<you>/agent-evals).
"""

import argparse
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from backend.agents.config import AgentSettings
from backend.agents.runtime import AgentRuntime, InlineExecutor
from backend.agents.server import build_runtime
from backend.contracts.agent_contract_v1 import AgentRunRequest
from evals.scorers import DETERMINISTIC

DATASET = Path(__file__).with_name("dataset.jsonl")
EVAL_USER = "eval.user@example.com"

Predict = Callable[..., dict[str, Any]]


def load_dataset(path: Path = DATASET) -> list[dict[str, Any]]:
    """Rows with complete contract requests: ids and ``meta`` are filled in where a row omits them."""
    rows = []
    with path.open() as lines:
        for index, line in enumerate(line for line in lines if line.strip()):
            row = json.loads(line)
            request = row["inputs"]["request"]
            run_id = request.setdefault("app_agent_run_id", f"eval-{index + 1}")
            request.setdefault("idempotency_key", run_id)
            request.setdefault(
                "meta", {"initiator": EVAL_USER, "submitted_at": "2026-01-01T00:00:00Z"}
            )
            AgentRunRequest.model_validate(request)  # fail early on a malformed row
            # Only what evaluate() takes: rows from from_feedback.py also carry the raw feedback.
            rows.append({"inputs": row["inputs"], "expectations": row.get("expectations", {})})
    return rows


def make_predict(runtime: AgentRuntime) -> Predict:
    def predict(request: dict[str, Any]) -> dict[str, Any]:
        run = AgentRunRequest.model_validate(request)
        runtime.submit(run)  # the inline executor finishes the run before submit returns
        status = runtime.poll(run.app_agent_run_id)
        assert status is not None
        return status.model_dump(mode="json", exclude_none=True)

    return predict


def evaluate_offline(rows: list[dict[str, Any]]) -> int:
    """Run the fake agent and the deterministic scorers; return the number of failed checks."""
    # Pinned, and no .env: a developer's local overrides must not change what is evaluated.
    settings = AgentSettings(
        _env_file=None,
        agent_runner="fake",
        agent_runner_overrides="",
        llm_endpoint=None,
        fake_agent_step_seconds=0,
        fake_agent_fail_at=None,
        fake_agent_drift="",
        mlflow_experiment_id=None,
        databricks_app_name=None,
    )
    predict = make_predict(build_runtime(settings, executor=InlineExecutor()))
    failures = 0
    for row in rows:
        request = row["inputs"]["request"]
        outputs = predict(**row["inputs"])
        results = []
        for check in DETERMINISTIC:
            feedback = check.run(
                inputs=row["inputs"], outputs=outputs, expectations=row.get("expectations")
            )
            if feedback is None:
                continue
            failures += feedback.value is not True
            results.append(f"{check.name}={'pass' if feedback.value else 'FAIL'}")
        print(f"{request['app_agent_run_id']:<8} {request['run_kind']:<15} {' '.join(results)}")
    print(f"\n{failures} failed checks across {len(rows)} rows")
    return failures


def evaluate_with_mlflow(
    rows: list[dict[str, Any]], *, profile: str, endpoint: str, experiment: str | None
) -> None:
    import mlflow
    from databricks.sdk import WorkspaceClient
    from mlflow.genai.scorers import Correctness, Safety

    user = WorkspaceClient(profile=profile).current_user.me().user_name
    mlflow.set_tracking_uri(f"databricks://{profile}")
    mlflow.set_experiment(experiment or f"/Users/{user}/agent-evals")
    mlflow.langchain.autolog()

    settings = AgentSettings(
        _env_file=None,
        agent_runner="real",
        agent_runner_overrides="",
        llm_endpoint=endpoint,
        mlflow_experiment_id=None,
    )
    # Inline: the model calls run in predict's thread, so they nest under the evaluation's trace.
    runtime = build_runtime(settings, executor=InlineExecutor())
    results = mlflow.genai.evaluate(
        data=rows,
        predict_fn=make_predict(runtime),
        # Judges for meaning; syntax (Markdown, length, contract) is checked by DETERMINISTIC.
        scorers=[Correctness(), Safety(), *DETERMINISTIC],
    )
    print(json.dumps(results.metrics, indent=2, default=str))
    print(f"MLflow run: {results.run_id}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dev", action="store_true", help="offline, with the fake agent")
    parser.add_argument("--endpoint", default=os.environ.get("LLM_ENDPOINT"))
    parser.add_argument("--experiment", help="MLflow experiment path")
    parser.add_argument("--dataset", type=Path, default=DATASET)
    args = parser.parse_args(argv)
    rows = load_dataset(args.dataset)

    if args.dev:
        sys.exit(1 if evaluate_offline(rows) else 0)

    profile = os.environ.get("DATABRICKS_CONFIG_PROFILE")
    if not profile:
        parser.error("set DATABRICKS_CONFIG_PROFILE (make eval PROFILE=...); no default profile")
    if not args.endpoint:
        parser.error("set --endpoint or LLM_ENDPOINT to a Model Serving endpoint")
    evaluate_with_mlflow(rows, profile=profile, endpoint=args.endpoint, experiment=args.experiment)


if __name__ == "__main__":
    main()
