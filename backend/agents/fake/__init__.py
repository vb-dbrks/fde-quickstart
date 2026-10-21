"""The fake agent: contract-identical, deterministic, no model calls.

Lets the app and UI be built and tested while the real agent is still being written (and runs in CI
without credentials). Select it with AGENT_RUNNER=fake, or per run kind with AGENT_RUNNER_OVERRIDES.
"""

from backend.agents.fake.runner import FakeAgent

__all__ = ["FakeAgent"]
