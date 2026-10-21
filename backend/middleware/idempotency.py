"""Idempotency-Key support for mutating /api requests.

A POST/PUT/PATCH/DELETE under /api with an ``Idempotency-Key`` header runs at most once per user and
key - a double click or a client retry after a dropped connection doesn't do the work twice:

- The key is claimed before the request runs. A second request with the same key while the first is
  still running gets 409 (retry shortly); once the first has finished, its stored response is
  replayed with the header ``Idempotent-Replayed: true``.
- Only successful (2xx) responses are stored. A failed request releases its claim, so the client can
  retry with the same key.
- A key used for a different method or path gets 422. Keys expire after 24 hours; a claim left behind
  by a request that crashed expires after CLAIM_TIMEOUT.
"""

import json
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from backend.auth.identity import principal_email
from backend.domain.models import IdempotencyKey

logger = logging.getLogger(__name__)

HEADER = "idempotency-key"
TTL = timedelta(hours=24)
CLAIM_TIMEOUT = timedelta(minutes=5)
_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

Sessions = async_sessionmaker[AsyncSession]


class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        key = request.headers.get(HEADER, "").strip()[:200]
        if not key or request.method not in _METHODS or not request.url.path.startswith("/api/"):
            return await call_next(request)
        principal = principal_email(request, request.app.state.settings)
        if principal is None:
            return await call_next(request)

        sessions: Sessions = request.app.state.sessionmaker
        stored = await _claim(sessions, key, principal, request.method, request.url.path)
        if stored is not None:
            return _answer_repeat(stored, request)

        try:
            response = await call_next(request)
        except BaseException:
            await _release(sessions, key, principal)
            raise
        body = b"".join([chunk async for chunk in response.body_iterator])  # type: ignore[attr-defined]
        headers = dict(response.headers)
        headers.pop("content-length", None)
        storable = not body or "application/json" in response.headers.get("content-type", "")
        if 200 <= response.status_code < 300 and storable:
            await _store(sessions, key, principal, response.status_code, body)
        else:
            await _release(sessions, key, principal)
        return Response(body, status_code=response.status_code, headers=headers)


async def _claim(
    sessions: Sessions, key: str, principal: str, method: str, path: str
) -> IdempotencyKey | None:
    """Claim the key for this request. Returns None if claimed, else the existing record."""
    now = datetime.now(UTC)
    async with sessions() as db:
        existing = await db.get(IdempotencyKey, (key, principal))
        if existing is not None and (
            existing.created_at < now - TTL
            or (existing.status_code is None and existing.created_at < now - CLAIM_TIMEOUT)
        ):
            await db.delete(existing)
            await db.flush()
        claimed = await db.scalar(
            insert(IdempotencyKey)
            .values(key=key, principal=principal, method=method, path=path)
            .on_conflict_do_nothing(index_elements=["key", "principal"])
            .returning(IdempotencyKey.key)
        )
        await db.commit()
        if claimed is not None:
            return None
        current = await db.get(IdempotencyKey, (key, principal), populate_existing=True)
        # Released between our insert and this read: report it as in progress; a retry claims it.
        return current or IdempotencyKey(key=key, principal=principal, method=method, path=path)


def _answer_repeat(stored: IdempotencyKey, request: Request) -> Response:
    if (stored.method, stored.path) != (request.method, request.url.path):
        return JSONResponse(
            {"detail": "This Idempotency-Key was already used for a different request."},
            status_code=422,
        )
    if stored.status_code is None:
        return JSONResponse(
            {"detail": "A request with this Idempotency-Key is still in progress. Retry shortly."},
            status_code=409,
            headers={"Retry-After": "2"},
        )
    headers = {"Idempotent-Replayed": "true"}
    if stored.response_body is None:  # e.g. 204 No Content: no body at all
        return Response(status_code=stored.status_code, headers=headers)
    return JSONResponse(stored.response_body, status_code=stored.status_code, headers=headers)


async def _store(
    sessions: Sessions, key: str, principal: str, status_code: int, body: bytes
) -> None:
    async with sessions() as db:
        record = await db.get(IdempotencyKey, (key, principal))
        if record is not None:
            record.status_code = status_code
            record.response_body = json.loads(body) if body else None
        await db.execute(
            delete(IdempotencyKey).where(IdempotencyKey.created_at < datetime.now(UTC) - TTL)
        )
        await db.commit()


async def _release(sessions: Sessions, key: str, principal: str) -> None:
    async with sessions() as db:
        await db.execute(
            delete(IdempotencyKey).where(
                IdempotencyKey.key == key,
                IdempotencyKey.principal == principal,
                IdempotencyKey.status_code.is_(None),
            )
        )
        await db.commit()
