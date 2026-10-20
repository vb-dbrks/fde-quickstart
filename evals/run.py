"""Evaluate the assistant agent with MLflow 3.

    make eval PROFILE=<cli-profile> LLM_ENDPOINT=<serving-endpoint>

The agent runs on your machine against a throwaway Postgres (pgserver) seeded with sample notes, and
calls the model endpoint in your CLI profile's workspace. Results are logged to an MLflow experiment in
that workspace (default: /Users/<you>/agent-evals). Add rows to dataset.jsonl as you learn what
users ask; add scorers to scorers.py.
"""

import argparse
import asyncio
import json
import os
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app import migrations, notes
from app.agents.assistant import AssistantAgent
from app.agents.base import AgentContext
from app.db import create_sessionmaker
from app.permissions.roles import Role, permissions_for
from app.permissions.service import Principal
from evals.scorers import concise

DATASET = Path(__file__).with_name("dataset.jsonl")
EVAL_USER = "eval.user@example.com"
SEED_NOTES = [
    ("Kick-off meeting", "The kick-off is on Monday at 10:00 in the main meeting room."),
    ("Decision: app state", "We decided to keep the app's state in Lakebase Postgres."),
    ("Action items", "Alex shares the demo dataset by Friday. Sam books the user interviews."),
]


def load_dataset(path: Path = DATASET) -> list[dict[str, Any]]:
    with path.open() as rows:
        return [json.loads(line) for line in rows if line.strip()]


@contextmanager
def seeded_database() -> Iterator[sessionmaker[Session]]:
    import pgserver

    pgdata = Path(tempfile.mkdtemp(prefix="pgeval-"))
    server = pgserver.get_server(pgdata, cleanup_mode="stop")
    engine = create_engine(server.get_uri().replace("postgresql://", "postgresql+psycopg://", 1))
    try:
        migrations.upgrade(engine)
        sessions = create_sessionmaker(engine)
        with sessions() as session:
            for title, body in SEED_NOTES:
                notes.create_note(session, owner="team.lead@example.com", title=title, body=body)
            session.commit()
        yield sessions
    finally:
        engine.dispose()
        server.cleanup()
        shutil.rmtree(pgdata, ignore_errors=True)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--endpoint", default=os.environ.get("LLM_ENDPOINT"))
    parser.add_argument("--experiment", help="MLflow experiment path")
    args = parser.parse_args(argv)
    profile = os.environ.get("DATABRICKS_CONFIG_PROFILE")
    if not profile:
        parser.error("set DATABRICKS_CONFIG_PROFILE (make eval PROFILE=...); no default profile")
    if not args.endpoint:
        parser.error("set --endpoint or LLM_ENDPOINT to a Model Serving endpoint")

    import mlflow
    from databricks.sdk import WorkspaceClient
    from mlflow.genai.scorers import Correctness, Guidelines, RelevanceToQuery, Safety

    user = WorkspaceClient(profile=profile).current_user.me().user_name
    mlflow.set_tracking_uri(f"databricks://{profile}")
    mlflow.set_experiment(args.experiment or f"/Users/{user}/agent-evals")
    mlflow.openai.autolog()

    eval_user = Principal(
        email=EVAL_USER,
        display_name="Eval user",
        roles=frozenset({Role.EDITOR}),
        permissions=permissions_for([Role.EDITOR]),
    )
    with seeded_database() as sessions:
        context = AgentContext(principal=eval_user, sessions=sessions)

        def predict(message: str) -> str:
            # A fresh agent per row: its HTTP client is tied to the event loop asyncio.run creates.
            return asyncio.run(AssistantAgent(args.endpoint).run(context, message)).output

        results = mlflow.genai.evaluate(
            data=load_dataset(),
            predict_fn=predict,
            scorers=[
                Correctness(),
                RelevanceToQuery(),
                Safety(),
                Guidelines(
                    # The app shows replies as plain text, so Markdown would appear literally.
                    # Length is checked by the deterministic `concise` scorer: judges miscount.
                    name="plain_text",
                    guidelines=(
                        "The response contains no Markdown formatting: no asterisks for bold or"
                        " italics, no bullet points or numbered lists, and no headings."
                    ),
                ),
                concise,
            ],
        )
    print(json.dumps(results.metrics, indent=2, default=str))
    print(f"MLflow run: {results.run_id}")


if __name__ == "__main__":
    main()
