"""Role-based access control.

* roles.py   - permissions the code checks, and the roles that bundle them
* service.py - resolving a user's effective roles; granting and revoking roles
* deps.py    - FastAPI dependencies: ``CurrentPrincipal`` and ``require(permission)``

Databricks Apps decides who can open the app at all (CAN_USE on the app). These roles decide what a
signed-in user can do inside it.
"""
