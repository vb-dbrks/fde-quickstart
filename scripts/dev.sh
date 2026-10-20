#!/usr/bin/env bash
# Local development: Postgres (pgserver), the API with auto-reload on :8000 and Vite on :5173.
# Open http://localhost:5173. Optional: PROFILE=<cli-profile> LLM_ENDPOINT=<endpoint> to use the agent.
set -euo pipefail
cd "$(dirname "$0")/.."

export PYTHONPATH=backend
DATABASE_URL="$(uv run --frozen --all-groups python scripts/localdb.py url)"
export DATABASE_URL
if [[ -n "${PROFILE:-}" ]]; then
  export DATABRICKS_CONFIG_PROFILE="$PROFILE"
fi
echo "Postgres: $DATABASE_URL (stop it with: uv run python scripts/localdb.py stop)"

trap 'kill 0' EXIT
uv run --frozen --all-groups uvicorn app.main:create_app --factory --reload --reload-dir backend --port 8000 &
npm --prefix frontend run dev &
wait
