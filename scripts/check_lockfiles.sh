#!/usr/bin/env bash
# Fail if a lockfile references anything other than the public PyPI / npm registries.
# Mirror URLs work on the machine that wrote them but break CI and Databricks Apps deploys.
set -euo pipefail
cd "$(dirname "$0")/.."

status=0

# uv.lock: every registry / file URL must be public PyPI.
bad_py=$(grep -oE 'https?://[^"/]+' uv.lock | sort -u | grep -vxE 'https://(pypi\.org|files\.pythonhosted\.org)' || true)
if [[ -n "$bad_py" ]]; then
  echo "uv.lock contains non-public hosts (run scripts/relock.sh):"
  echo "$bad_py" | sed 's/^/  /'
  status=1
fi

# package-lock.json: frontend/.npmrc omits registry "resolved" URLs; any that remain must be npmjs.
lock=frontend/package-lock.json
if [[ -f "$lock" ]]; then
  bad_npm=$(grep -oE '"resolved": "https?://[^"/]+' "$lock" | sed 's/"resolved": "//' | sort -u \
    | grep -vx 'https://registry.npmjs.org' || true)
  if [[ -n "$bad_npm" ]]; then
    echo "$lock contains non-public registries (delete it and run npm install in frontend/):"
    echo "$bad_npm" | sed 's/^/  /'
    status=1
  fi
fi

if [[ $status -eq 0 ]]; then
  echo "lockfiles OK: public registries only"
fi
exit $status
