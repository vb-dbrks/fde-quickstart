"""Run the agent on its own: as a second Databricks App (on DATABRICKS_APP_PORT) or locally.

Locally, prefer `make agent` (auto-reload on :9000).
"""

import logging
import os

import uvicorn


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    uvicorn.run(
        "backend.agents.server:create_agent_app",
        factory=True,
        host="0.0.0.0",  # noqa: S104 - Databricks Apps routes traffic to the container, not localhost
        port=int(os.environ.get("DATABRICKS_APP_PORT", "9000")),
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
