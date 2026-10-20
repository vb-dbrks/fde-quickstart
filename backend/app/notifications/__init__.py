"""Notifications.

* channels.py - where a notification goes: the in-app inbox (always) plus optional outbound channels
* service.py  - ``Notifier.notify()`` for sending, and queries for the bell menu

The UI polls ``GET /api/notifications`` every 30 seconds. The Apps proxy buffers server-sent events and
cuts requests off after 120 seconds, so polling is the simple, reliable default.
"""
