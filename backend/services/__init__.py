"""Business logic. Routes call services; services use the database and the agent client.

* documents.py             - create, read, edit, share documents (fields per the field catalog)
* agent_runs.py            - start runs, refresh them from the agent, finish them (ADR 0003)
* agent_client.py          - the agent contract over in-process ASGI or HTTP
* agent_payload_builder.py - the full-context request for each run (ADR 0004)
* materialise.py           - write a generate run's output to the document, atomically
* assistant.py             - assistant threads and messages
* notifications.py         - in-app notifications (+ notification_channels.py)
"""
