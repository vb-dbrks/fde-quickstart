"""The agent runtime: stateless inference behind the agent contract (contracts/agent-api-contract.md).

* server.py   - FastAPI app: POST /agent/run, GET /agent/run/{id}, GET /contract, GET /healthz
* runtime.py  - accepts runs, executes them on a thread pool, keeps their status until polled
* runners/    - real runners, one per run kind (LangChain on a Databricks model endpoint)
* fake/       - the fake agent: same contract, deterministic output, for building the app in parallel
* prompts/    - system prompts, one Markdown file per run kind
* config.py   - runtime settings (LLM_ENDPOINT, AGENT_RUNNER, FAKE_AGENT_*)

Rules (enforced by tests/agents/test_boundary.py): nothing here imports the app's database, services
or API - only ``backend.contracts``. Everything the agent needs arrives in the request; everything
it produces goes back in the response, and the app decides what to store.

In a single-app deployment the app runs this runtime in-process (AGENT_TRANSPORT=inprocess). Run it
on its own with `make agent`, or deploy it as a separate Databricks App, without code changes.
"""
