---
title: "0008: Notifications by polling"
sidebar_label: "0008: Notifications"
---

# 0008: Notifications by polling

**Status:** Accepted

## Context

Users should learn that a run finished or failed, or that they were granted a role, even if they
moved on. Push channels (WebSockets, server-sent events) are unreliable behind the Databricks Apps
proxy, which buffers streamed responses and times requests out after 120 seconds.

## Decision

- Notifications are rows in `notifications`, written in the same transaction as the change that caused
  them (`backend/services/notifications.py`).
- The bell menu polls `GET /api/notifications` every 30 seconds and shows a toast for new ones.
- Agent run pages poll the run itself (ADR 0003), so they don't wait for the bell.
- Outbound channels are pluggable (`backend/services/notification_channels.py`). A Slack-compatible
  webhook is built in: set `NOTIFICATION_WEBHOOK_URL`, ideally from a secret resource. A failed
  delivery is logged and never rolls back the change.

## Consequences

- Works behind the proxy with no extra infrastructure.
- A notification appears up to 30 seconds late in the bell.
- Email or chat delivery is a new channel class, not a change to callers.
