"""Who is calling.

On Databricks Apps the proxy signs the user in and forwards their identity in X-Forwarded-* headers;
the app cannot be reached any other way. Off-platform (`make dev`, tests) the request may carry the
header itself, otherwise a configurable stand-in user is used.
"""

from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from backend.settings import Settings


@dataclass(frozen=True)
class Identity:
    email: str
    display_name: str


def identity_from_request(request: Request, settings: Settings) -> Identity:
    email = request.headers.get("x-forwarded-email", "").strip().lower()
    if email:
        name = request.headers.get("x-forwarded-preferred-username") or email
        return Identity(email=email, display_name=name)
    if settings.on_databricks:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No user identity in the request.")
    return Identity(email=settings.dev_user_email.lower(), display_name="Local developer")


def principal_email(request: Request, settings: Settings) -> str | None:
    """The caller's email without failing; used by middleware that runs before routing."""
    email = request.headers.get("x-forwarded-email", "").strip().lower()
    if email:
        return email
    return None if settings.on_databricks else settings.dev_user_email.lower()
