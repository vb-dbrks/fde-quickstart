"""Authentication and authorization.

* identity.py  - who is calling (Databricks Apps forwards the signed-in user in X-Forwarded-* headers)
* roles.py     - app-wide permissions and the roles that bundle them
* principal.py - a user's effective roles; granting and revoking roles
* access.py    - per-document access (owner / edit / view)
* deps.py      - FastAPI dependencies: ``CurrentPrincipal`` and ``require(permission)``

Databricks Apps decides who can open the app at all (CAN_USE on the app). Roles decide what a
signed-in user can do; document access decides which documents they can see and change.
"""
