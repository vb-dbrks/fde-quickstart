"""Settings for the agent runtime. Independent of the app's settings so the runtime can run alone."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.contracts.agent_contract_v1 import RUN_KINDS

RunnerChoice = Literal["fake", "real"]


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    agent_version: str = "0.1.0"
    # Model Serving endpoint for the real runners (e.g. a Foundation Model API endpoint).
    llm_endpoint: str | None = None
    # fake or real for every run kind. Unset: real when LLM_ENDPOINT is set, otherwise fake.
    agent_runner: RunnerChoice | None = None
    # Per run kind, e.g. "assistant_turn=real,generate=fake". Wins over AGENT_RUNNER.
    agent_runner_overrides: str = ""
    agent_max_workers: int = 4
    # Finished runs kept for polling; the oldest are dropped first.
    agent_max_runs_kept: int = 1000

    # Fake agent knobs (the same ideas as a standalone fake agent app).
    fake_agent_step_seconds: float = 1.0
    fake_agent_fail_at: str | None = None  # fail the run at this step name
    fake_agent_version: str = "fake-agent"
    fake_agent_drift: str = ""  # prefixed to generated text, to make outputs differ on replay

    # MLflow experiment that receives a trace per run. Unset disables tracing.
    mlflow_experiment_id: str | None = None

    def runner_for(self, run_kind: str) -> RunnerChoice:
        overrides = dict(
            item.split("=", 1) for item in self.agent_runner_overrides.split(",") if "=" in item
        )
        choice = overrides.get(run_kind, "").strip() or self.agent_runner
        if choice in ("fake", "real"):
            return "fake" if choice == "fake" else "real"
        return "real" if self.llm_endpoint else "fake"

    def runner_choices(self) -> dict[str, RunnerChoice]:
        return {kind: self.runner_for(kind) for kind in RUN_KINDS}
