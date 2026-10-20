"""Local Postgres for `make dev` and `make migration`, via pgserver (no Docker).

    python scripts/localdb.py url    # start if needed, print a SQLAlchemy URL
    python scripts/localdb.py stop   # stop it

The data directory lives under ~/.cache (override with LOCAL_PGDATA): Postgres puts its Unix socket
there, and socket paths are limited to about 100 characters, which deep repo paths exceed.
"""

import hashlib
import os
import sys
from pathlib import Path

import pgserver

REPO = Path(__file__).resolve().parents[1]


def data_dir() -> Path:
    if override := os.environ.get("LOCAL_PGDATA"):
        return Path(override)
    repo_hash = hashlib.sha256(str(REPO).encode()).hexdigest()[:10]
    return Path.home() / ".cache" / "databricks-app-dev" / f"pg-{repo_hash}"


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else "url"
    pgdata = data_dir()
    pgdata.mkdir(parents=True, exist_ok=True)
    if command == "url":
        server = pgserver.get_server(pgdata, cleanup_mode=None)  # keep running after we exit
        print(server.get_uri().replace("postgresql://", "postgresql+psycopg://", 1))
    elif command == "stop":
        pgserver.get_server(pgdata, cleanup_mode="stop").cleanup()
        print(f"Stopped Postgres in {pgdata}")
    else:
        sys.exit(f"unknown command {command!r}; use 'url' or 'stop'")


if __name__ == "__main__":
    main()
