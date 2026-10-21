"""Enums stored in the database or returned by the API."""

from enum import StrEnum


class RunStatus(StrEnum):
    """Lifecycle of an ``agent_runs`` row.

    ``queued`` is app-only (the row exists, the agent has not accepted it yet); the other values are
    the agent contract's statuses, mirrored as the app polls.
    """

    QUEUED = "queued"
    ACCEPTED = "accepted"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

    @property
    def terminal(self) -> bool:
        return self in (RunStatus.SUCCEEDED, RunStatus.FAILED)


# Runs still in progress: the poller sweeps them and the UI resumes watching them.
ACTIVE_RUN_STATUSES = (RunStatus.QUEUED.value, RunStatus.ACCEPTED.value, RunStatus.RUNNING.value)


class Access(StrEnum):
    """Per-document access, from least to most."""

    VIEW = "view"
    EDIT = "edit"
    OWNER = "owner"

    @property
    def rank(self) -> int:
        return _ACCESS_RANK[self]

    def allows(self, minimum: "Access") -> bool:
        return self.rank >= minimum.rank


_ACCESS_RANK = {Access.VIEW: 1, Access.EDIT: 2, Access.OWNER: 3}


class FieldSource(StrEnum):
    USER = "user"
    AGENT = "agent"


class AuditAction(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    GENERATE = "generate"
    REGENERATE = "regenerate"
    ACCEPT_SUGGESTION = "accept_suggestion"
    SHARE = "share"
    UNSHARE = "unshare"
    DELETE = "delete"
