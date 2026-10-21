---
title: Permissions
---

# Permissions

Two layers decide what a user can do (ADR 0007). Both are checked in the API on every request; the UI
only hides what the user can't do.

## Who the user is

On Databricks Apps the proxy signs users in and forwards their identity in `X-Forwarded-Email`
(`backend/auth/identity.py`). A request without it is rejected. Off-platform, requests run as
`DEV_USER_EMAIL`.

## App-wide roles and permissions

Defined in `backend/auth/roles.py`. Code checks permissions; roles are named sets of them.

| Permission | Allows |
| --- | --- |
| `documents:create` | Creating documents. |
| `agents:run` | Starting agent runs: generate, enhance, assistant. |
| `documents:access_any` | Owner access to every document. |
| `roles:manage` | Granting and revoking roles (**Users & roles**). |

| Role | Permissions |
| --- | --- |
| `viewer` | none: sees only documents shared with them |
| `editor` | `documents:create`, `agents:run` |
| `admin` | all of the above |

Every user has the default role (`APP_DEFAULT_ROLE`, `viewer`). Admins grant more roles in the UI;
assignments are stored in `role_assignments`, and the user gets a notification. Emails in
`APP_ADMIN_EMAILS` are always admins, so a new deployment has someone who can grant roles.

In a route, require a permission with the `require` dependency from `backend/auth/deps.py`. In the UI,
wrap actions in `<Can permission="...">` or guard routes with `<RequirePermission>`.

## Per-document access

Defined in `backend/auth/access.py`, stored in `document_access`.

| Access | Allows |
| --- | --- |
| `view` | Reading the document, its history, and starting assistant conversations about it. |
| `edit` | Also editing fields, generating and enhancing. |
| `owner` | Also sharing, unsharing and deleting. |

- The creator is the first owner. A document always keeps at least one owner.
- `require_document(db, principal, document_id, minimum)` loads a document for a request. **No access
  answers 404**, so the API doesn't reveal that a document exists; **too little access answers 403**.
- Running an agent needs `agents:run` and, for `generate` and `enhance_field`, edit access.
- Source documents for a run are filtered to those the user can see.
- Conversations and assistant runs are visible only to the user who started them.

## Adding a permission

1. Add it to `Permission` and to the roles that should have it in `ROLE_PERMISSIONS`.
2. Check it in the API with `require(...)` or `principal.can(...)`.
3. `make api-types`; the UI's `Permission` type picks it up. Use `<Can>` where it matters.
4. Test both sides: allowed and denied.
