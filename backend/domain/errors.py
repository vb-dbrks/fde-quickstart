"""Errors raised by services. backend.main maps them to HTTP responses."""


class DomainError(Exception):
    status_code = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    """Missing - or not visible to the caller (we never reveal that a document exists)."""

    status_code = 404


class ForbiddenError(DomainError):
    """Visible to the caller, but they lack the access or permission for this action."""

    status_code = 403


class ConflictError(DomainError):
    status_code = 409


class InvalidInputError(DomainError):
    status_code = 422
