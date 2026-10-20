"""Agents served at ``/api/agents/{name}``.

* base.py      - the ``AppAgent`` protocol and the ``AgentContext`` that tools receive
* tools.py     - tools; they act as the calling user and check the same permissions as the API
* llm.py       - OpenAI-compatible client for Databricks Model Serving
* assistant.py - example agent built with the OpenAI Agents SDK
* registry.py  - which agents are exposed, and MLflow tracing setup
* prompts/     - system prompts, one Markdown file per agent

Keep this package inside ``app``: a top-level ``agents`` package would shadow the OpenAI Agents SDK,
which is also imported as ``agents``.
"""
