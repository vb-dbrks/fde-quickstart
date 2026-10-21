#!/usr/bin/env bash
# Local development: Postgres (pgserver), the API with auto-reload on :8000 and Vite on :5173.
# Open http://localhost:5173. The agent runs in-process with the fake runner unless LLM_ENDPOINT is
# set (then PROFILE=<cli-profile> authenticates the model calls). To use a separately running agent
# (`make agent`), set AGENT_TRANSPORT=http AGENT_API_BASE=http://localhost:9000.
set -euo pipefail
cd "$(dirname "$0")/.."

export PYTHONPATH=.
DATABASE_URL="$(uv run --frozen --all-groups python scripts/localdb.py url)"
export DATABASE_URL
if [[ -n "${PROFILE:-}" ]]; then
  export DATABRICKS_CONFIG_PROFILE="$PROFILE"
fi
echo "Postgres: $DATABASE_URL (stop it with: make db-stop)"
echo "Agent transport: ${AGENT_TRANSPORT:-inprocess} (the runner per run kind is on the Home page)"

trap 'kill 0' EXIT
uv run --frozen --all-groups uvicorn backend.main:create_app --factory --reload \
  --reload-dir backend --reload-dir contracts --port 8000 &
npm --prefix frontend run dev &
wait
