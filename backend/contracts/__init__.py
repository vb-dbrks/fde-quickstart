"""The contract between the app and the agent runtime - the only code both sides import.

* agent_contract_v1.py - wire models for POST /agent/run and GET /agent/run/{id}
* field_catalog.py     - loads contracts/field-catalog.yaml (document types and their fields)
* validation.py        - checks an agent's output against the request and the catalog

The golden record is contracts/agent-api-contract.md; tests/contracts keep the two in sync.
"""
