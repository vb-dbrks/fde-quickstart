"""Runtime settings, read from environment variables (and `.env` when running locally)."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.permissions.roles import Role

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

    # Model Serving endpoint the agents call. Unset disables the agents.
    llm_endpoint: str | None = None
    # MLflow experiment that receives agent traces. Unset disables tracing.
    mlflow_experiment_id: str | None = None
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
