"""Turn users' feedback into evaluation rows.

    make eval-dataset PROFILE=<cli-profile> EXPERIMENT=<id or path> [DAYS=30] [UC_TABLE=cat.schema.table]

Users rate fields and answers, accept or dismiss suggestions, and correct values the agent wrote. The
app stores all of it on each run's MLflow trace (services/feedback.py, contract section 7). This
searches the agent's experiment for traces with that feedback and writes one row per trace, in the
format of dataset.jsonl:

- ``inputs.request``: the request the agent received (the trace's root span inputs) - the row
  replays exactly what the user saw;
- ``expectations.expected_facts``: the values users corrected fields to, which the Correctness judge
  checks the output against;
- ``feedback``: the ratings with their reasons and comments, for a person to review.

Rows go to evals/feedback_dataset.jsonl (git-ignored: it holds real user content). Review them - a
row rated down without a correction needs a person to write its expected facts - then copy the good
ones into dataset.jsonl. With UC_TABLE, rows that have expected facts are also merged into a Unity
Catalog evaluation dataset, which `mlflow.genai.evaluate` and the Databricks UI use directly.
"""

import argparse
import json
import os
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

OUT = Path(__file__).with_name("feedback_dataset.jsonl")
_FEEDBACK_METADATA = ("field_path", "reasons", "message_id")


def rows_from_traces(traces: Iterable[Any]) -> list[dict[str, Any]]:
    """Rows for traces of agent runs that have feedback from people (current assessments only)."""
    rows = []
    for trace in traces:
        human = [a for a in trace.search_assessments() if a.source.source_type == "HUMAN"]
        request = json.loads(trace.data.request) if trace.data.request else None
        if not human or not isinstance(request, dict) or "run_kind" not in request:
            continue
        # Keyed by the field path in metadata (assessment names can't hold the path's dots).
        corrections = {
            (a.metadata or {}).get("field_path", a.name): a.expectation.value
            for a in human
            if a.expectation is not None
        }
        ratings = [
            {
                "name": a.name,
                "value": a.feedback.value,
                "comment": a.rationale,
                "user": a.source.source_id,
                **{k: v for k, v in (a.metadata or {}).items() if k in _FEEDBACK_METADATA},
            }
            for a in human
            if a.feedback is not None
        ]
        facts = [f"{path}: {_as_text(value)}" for path, value in sorted(corrections.items())]
        rows.append(
            {
                "inputs": {"request": request},
                "expectations": {"expected_facts": facts},
                "feedback": ratings,
                "trace_id": trace.info.trace_id,
            }
        )
    return rows


def _as_text(value: Any) -> str:
    return "; ".join(map(str, value)) if isinstance(value, list) else str(value)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--experiment", required=True, help="the agent's experiment id or path")
    parser.add_argument("--days", type=int, default=30, help="look at traces this recent")
    parser.add_argument("--max-traces", type=int, default=1000)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--uc-table", help="also merge rows into this UC evaluation dataset")
    args = parser.parse_args(argv)
    profile = os.environ.get("DATABRICKS_CONFIG_PROFILE")
    if not profile:
        parser.error("set DATABRICKS_CONFIG_PROFILE (make eval-dataset PROFILE=...)")

    import mlflow

    mlflow.set_tracking_uri(f"databricks://{profile}")
    experiment_id = args.experiment
    if not experiment_id.isdigit():
        experiment = mlflow.get_experiment_by_name(experiment_id)
        if experiment is None:
            parser.error(f"no experiment {experiment_id!r}")
        experiment_id = experiment.experiment_id
    # The agent tags traces when it stores feedback on them; Databricks' trace search filters on tags.
    traces = mlflow.search_traces(
        locations=[experiment_id],
        filter_string="tags.has_feedback = 'true'",
        max_results=args.max_traces,
        return_type="list",
    )
    since_ms = int((time.time() - args.days * 86_400) * 1000)
    rows = rows_from_traces(t for t in traces if t.info.timestamp_ms >= since_ms)
    with args.out.open("w") as out:
        for row in rows:
            out.write(json.dumps(row) + "\n")
    with_facts = [r for r in rows if r["expectations"]["expected_facts"]]
    print(f"{len(rows)} traces with feedback ({len(with_facts)} with corrections) -> {args.out}")

    if args.uc_table and with_facts:
        from mlflow.genai.datasets import create_dataset, get_dataset

        try:
            dataset = get_dataset(name=args.uc_table)
        except Exception:
            dataset = create_dataset(name=args.uc_table, experiment_id=[experiment_id])
        dataset.merge_records(
            [{"inputs": r["inputs"], "expectations": r["expectations"]} for r in with_facts]
        )
        print(f"merged {len(with_facts)} rows into {args.uc_table}")


if __name__ == "__main__":
    main()
