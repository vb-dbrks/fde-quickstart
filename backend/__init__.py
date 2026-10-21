"""The app: FastAPI backend (api -> services -> db/repositories -> domain) and the agent runtime.

Entry point: ``python -m backend`` (see app.yaml). ``backend.agents`` is the stateless agent runtime;
it talks to the rest of the app only through ``backend.contracts``.
"""
