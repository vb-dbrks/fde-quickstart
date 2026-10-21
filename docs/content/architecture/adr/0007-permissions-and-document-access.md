---
title: "0007: Roles, permissions and per-document access"
sidebar_label: "0007: Permissions"
---

# 0007: Roles, permissions and per-document access

**Status:** Accepted

## Context

Databricks Apps signs users in, and the app's users group decides who can open it. Inside the app,
some users may create documents and run agents while others only read, and each document is private
to the people it is shared with.

## Decision

Two independent layers:

- **App-wide roles** (`backend/auth/roles.py`). Code checks permissions, never role names. Roles are
  named sets of permissions: `viewer` (none), `editor` (`documents:create`, `agents:run`) and `admin`
  (all, including `roles:manage` and `documents:access_any`). Every user has the default role
  (`APP_DEFAULT_ROLE`, viewer); admins grant more in the UI; `APP_ADMIN_EMAILS` are always admins.
- **Per-document access** (`backend/auth/access.py`): `view`, `edit` or `owner` in `document_access`.
  The creator is the first owner; owners share and unshare; a document always keeps one owner.
  `documents:access_any` makes a user owner of every document.

No access at all answers 404, so the API never reveals that a document exists. Too little access
answers 403. The UI hides what a user can't do; the API enforces it regardless.

## Consequences

- Running an agent needs both: the `agents:run` permission and, for `generate` and `enhance_field`,
  edit access to the document. Source documents the user can't see are left out of the request.
- Conversations and assistant runs are private to the user who started them, even on shared documents.
- Adding a permission is a code change in one file; assigning roles is data.
