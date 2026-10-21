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
    # Sampling temperature. Unset: the endpoint's default (some models reject the parameter).
    llm_temperature: float | None = None
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

    # Set by Databricks Apps. There, the fake agent must be asked for (AGENT_RUNNER=fake): a missing
    # LLM_ENDPOINT fails at startup instead of quietly writing fake text into real documents.
    databricks_app_name: str | None = None

    def overrides(self) -> dict[str, str]:
        pairs = (
            item.split("=", 1) for item in self.agent_runner_overrides.split(",") if "=" in item
        )
        return {kind.strip(): choice.strip() for kind, choice in pairs}

    def runner_for(self, run_kind: str) -> RunnerChoice:
        choice = self.overrides().get(run_kind) or self.agent_runner
        if choice in ("fake", "real"):
            return "fake" if choice == "fake" else "real"
        return "real" if self.llm_endpoint else "fake"

    def check(self) -> None:
        """Refuse settings that would silently do the wrong thing."""
        unknown = sorted(set(self.overrides()) - set(RUN_KINDS))
        if unknown:
            raise RuntimeError(f"AGENT_RUNNER_OVERRIDES names unknown run kinds: {unknown}")
        implicit_fake = [
            kind
            for kind in RUN_KINDS
            if self.runner_for(kind) == "fake"
            and "fake" not in (self.overrides().get(kind), self.agent_runner)
        ]
        if self.databricks_app_name and implicit_fake:
            raise RuntimeError(
                "LLM_ENDPOINT is not set, so the agent would use the fake runner for "
                f"{', '.join(implicit_fake)}. Set LLM_ENDPOINT, or AGENT_RUNNER=fake on purpose."
            )

    def runner_choices(self) -> dict[str, RunnerChoice]:
        return {kind: self.runner_for(kind) for kind in RUN_KINDS}
