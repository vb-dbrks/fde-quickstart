"""Idempotency-Key support for mutating /api requests.

A POST/PUT/PATCH/DELETE under /api with an ``Idempotency-Key`` header is answered once; repeating it
(a double click, a client retry after a dropped connection) replays the stored response instead of
doing the work again. Keys are per user and expire after 24 hours. Only successful (2xx) JSON
responses are stored, so a failed request can simply be retried.
"""

import json
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from backend.auth.identity import principal_email
from backend.domain.models import IdempotencyKey

logger = logging.getLogger(__name__)

HEADER = "idempotency-key"
TTL = timedelta(hours=24)
_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        key = request.headers.get(HEADER, "").strip()[:200]
        if not key or request.method not in _METHODS or not request.url.path.startswith("/api/"):
            return await call_next(request)
        principal = principal_email(request, request.app.state.settings)
        if principal is None:
            return await call_next(request)

        sessions = request.app.state.sessionmaker
        async with sessions() as db:
            stored = await db.get(IdempotencyKey, (key, principal))
            if stored is not None and stored.created_at < datetime.now(UTC) - TTL:
                await db.delete(stored)
                await db.commit()
                stored = None
        if stored is not None:
            if (stored.method, stored.path) != (request.method, request.url.path):
                return JSONResponse(
                    {"detail": "This Idempotency-Key was already used for a different request."},
                    status_code=422,
                )
            return JSONResponse(
                stored.response_body,
                status_code=stored.status_code,
                headers={"Idempotent-Replayed": "true"},
            )

        response = await call_next(request)
        if not (200 <= response.status_code < 300):
            return response
        body = b"".join([chunk async for chunk in response.body_iterator])  # type: ignore[attr-defined]
        headers = dict(response.headers)
        headers.pop("content-length", None)
        if "application/json" in response.headers.get("content-type", "") or not body:
            async with sessions() as db:
                db.add(
                    IdempotencyKey(
                        key=key,
                        principal=principal,
                        method=request.method,
                        path=request.url.path,
                        status_code=response.status_code,
                        response_body=json.loads(body) if body else None,
                    )
                )
                await db.execute(
                    delete(IdempotencyKey).where(
                        IdempotencyKey.created_at < datetime.now(UTC) - TTL
                    )
                )
                try:
                    await db.commit()
                except IntegrityError:  # a concurrent request with the same key won the race
                    await db.rollback()
        return Response(body, status_code=response.status_code, headers=headers)
