"""Settings for the app process, read from environment variables (and `.env` when running locally).

The agent runtime has its own settings (backend.agents.config) so it can also run on its own.
"""

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.auth.roles import Role

STATIC_DIR = Path(__file__).parent / "static"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_title: str = "Quickstart App"

    # Local development and tests: a SQLAlchemy URL, e.g. the pgserver instance started by `make dev`.
    database_url: str | None = None

    # Lakebase connection details, injected by Databricks Apps for the app's `postgres` resource.
    pghost: str | None = None
    pgport: int = 5432
    pgdatabase: str | None = None
    pguser: str | None = None
    pgsslmode: str = "require"
    pgappname: str | None = None

    # Set by Databricks Apps. When present, identity must come from the Apps proxy headers.
    databricks_app_name: str | None = None

    # Comma-separated emails that are always admins, so a new deployment has someone who can grant roles.
    app_admin_emails: str = ""
    # Role every signed-in user has on top of the roles assigned to them.
    app_default_role: Role = Role.VIEWER
    # Identity used off-platform (make dev, tests) when a request has no X-Forwarded-Email header.
    dev_user_email: str = "dev.user@example.com"

    # Agent handoff. `inprocess` calls the agent runtime inside this process through the same HTTP
    # contract; `http` calls an agent deployed elsewhere (its own app, or `make agent` locally).
    agent_transport: Literal["inprocess", "http"] = "inprocess"
    agent_api_base: str | None = None
    agent_request_timeout_seconds: float = 30.0
    # Runs that have not finished after this long are failed with code TIMEOUT.
    agent_run_timeout_seconds: int = 600
    # Background poller that finishes runs nobody is watching (ADR 0003).
    poller_enabled: bool = True
    poller_interval_seconds: int = 10
    # Users' feedback goes to the run's MLflow trace right after it is given; this worker retries
    # what didn't get through (same switch as the poller).
    feedback_retry_interval_seconds: int = 30
    # Chat turns sent to the agent with each assistant message (oldest first, newest kept).
    assistant_history_limit: int = 20

    # Optional Slack-compatible incoming webhook that also receives notifications.
    notification_webhook_url: str | None = None

    run_migrations: bool = True
    static_dir: Path = STATIC_DIR

    @property
    def on_databricks(self) -> bool:
        return bool(self.databricks_app_name)

    @property
    def admin_emails(self) -> frozenset[str]:
        return frozenset(e.strip().lower() for e in self.app_admin_emails.split(",") if e.strip())
