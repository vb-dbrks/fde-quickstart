"""Run the app with uvicorn on the port Databricks Apps assigns (DATABRICKS_APP_PORT, 8000 locally)."""

import logging
import os

import uvicorn


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    uvicorn.run(
        "backend.main:create_app",
        factory=True,
        host="0.0.0.0",  # noqa: S104 - Databricks Apps routes traffic to the container, not localhost
        port=int(os.environ.get("DATABRICKS_APP_PORT", "8000")),
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
