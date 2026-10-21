#!/usr/bin/env bash
# Re-lock uv.lock so every URL in it points at public PyPI.
#
# CI and Databricks Apps install from the lockfile, so it must only contain public URLs. Where pypi.org
# is not reachable and packages come from a PyPI mirror (a corporate proxy), set PYPI_MIRROR to the
# mirror's simple index, e.g. https://pypi-mirror.example.com/simple: this resolves through it and
# rewrites the mirror URLs to their public equivalents. The mirror serves the same file paths, sizes
# and hashes, so only the host changes.
#
# Usage: [PYPI_MIRROR=<url>] scripts/relock.sh [extra `uv lock` args, e.g. --upgrade-package fastapi]
set -euo pipefail
cd "$(dirname "$0")/.."

PUBLIC_INDEX="https://pypi.org/simple"
PUBLIC_FILES="https://files.pythonhosted.org/packages/"

mirror="${PYPI_MIRROR:-}"
if [[ -z "$mirror" ]] && ! curl -sfI -m 5 "$PUBLIC_INDEX/pip/" >/dev/null 2>&1; then
  echo "pypi.org is not reachable. Set PYPI_MIRROR to your PyPI mirror's simple index and re-run." >&2
  exit 1
fi

# Index settings from the environment or uv.toml would leak into the lockfile; ignore them.
unset UV_INDEX UV_INDEX_URL UV_DEFAULT_INDEX UV_EXTRA_INDEX_URL

if [[ -z "$mirror" ]]; then
  uv lock --no-config "$@"
else
  echo "pypi.org is not reachable; locking through $mirror"
  uv lock --no-config --default-index "$mirror" "$@"
  base="${mirror%/}"
  base="${base%/simple}"
  python3 - "$base" "$PUBLIC_INDEX" "$PUBLIC_FILES" <<'PY'
import pathlib
import sys

base, public_index, public_files = sys.argv[1:]
lock = pathlib.Path("uv.lock")
text = lock.read_text()
text = text.replace(f"{base}/simple", public_index).replace(f"{base}/packages/", public_files)
lock.write_text(text)
PY
fi

scripts/check_lockfiles.sh
