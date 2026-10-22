"""Generic application APIs. Example-specific work is delegated to registered callbacks."""

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.api.deps import AgentClientDep, DeliverFeedback, SessionDep
from backend.auth.deps import CurrentPrincipal
from backend.auth.identity import identity_from_request
from backend.auth.principal import resolve_principal
from backend.auth.roles import Permission
from backend.domain.errors import ConflictError, ForbiddenError, InvalidInputError, NotFoundError
from backend.domain.models import (
    AgentRun,
    Message,
    RunEvent,
    Thread,
    ToolOutcome,
)
from backend.domain.schemas import MessageOut, RatingIn
from backend.services import feedback, interactions
from backend.services.agent_client import AgentClientError
from backend.services.interactions import AgentApplication

router = APIRouter(tags=["agent interactions"])


def registry(request: Request) -> dict[str, AgentApplication]:
    return cast(dict[str, AgentApplication], request.app.state.agent_applications)


class StartInteraction(BaseModel):
    agent_id: str
    input: dict[str, Any]
    session_id: str | None = None


class InteractionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    agent_id: str
    thread_id: str | None
    status: str
    result: dict[str, Any] | None
    error_message: str | None
    created_at: datetime


class SessionCreate(BaseModel):
    agent_id: str
    title: str = Field(default="New conversation", min_length=1, max_length=200)


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    agent_id: str
    title: str
    created_at: datetime


@router.get("/examples")
async def examples(request: Request) -> list[str]:
    return sorted({a.example for a in registry(request).values()})


@router.get("/agents")
async def agents(request: Request, client: AgentClientDep) -> list[dict[str, Any]]:
    enabled = registry(request)
    try:
        descriptors = [
            d.model_dump(mode="json") for d in await client.definitions() if d.id in enabled
        ]
    except (ValueError, AgentClientError) as exc:
        raise HTTPException(
            503, "Agent discovery requires a compatible execution v2 runtime"
        ) from exc
    for key, app in enabled.items():
        if app.execution_version == "v1":
            descriptors.append(
                {
                    "id": key,
                    "example": app.example,
                    "description": "Document workflow through the v1 compatibility routes",
                    "input_schema": app.input_model.model_json_schema(),
                    "result_schema": app.result_model.model_json_schema(),
                    "capabilities": ["state", "tools", "review"],
                    "tools": [
                        {
                            "name": name,
                            "description": "Focus a known document field",
                            "parameters": schema.model_json_schema(),
                        }
                        for name, schema in app.tools.items()
                    ],
                }
            )
    return descriptors


@router.post("/sessions", status_code=201)
async def create_session(
    payload: SessionCreate, request: Request, db: SessionDep, principal: CurrentPrincipal
) -> SessionOut:
    if not principal.can(Permission.AGENTS_RUN):
        raise ForbiddenError("Missing permission: agents:run")
    if payload.agent_id not in registry(request):
        raise NotFoundError("Agent not enabled")
    row = Thread(agent_id=payload.agent_id, owner=principal.email, title=payload.title)
    db.add(row)
    await db.commit()
    return SessionOut.model_validate(row)


@router.get("/sessions")
async def sessions(
    request: Request, db: SessionDep, principal: CurrentPrincipal, agent_id: str
) -> list[SessionOut]:
    if agent_id not in registry(request):
        raise NotFoundError("Agent not enabled")
    rows = await db.scalars(
        select(Thread)
        .where(Thread.agent_id == agent_id, Thread.owner == principal.email)
        .order_by(Thread.created_at.desc())
    )
    return [SessionOut.model_validate(row) for row in rows]


@router.get("/sessions/{session_id}/messages")
async def messages(
    session_id: str, db: SessionDep, principal: CurrentPrincipal, request: Request
) -> list[MessageOut]:
    session = await db.get(Thread, session_id)
    if (
        session is None
        or session.owner != principal.email
        or session.agent_id not in registry(request)
    ):
        raise NotFoundError("Session not found")
    rows = await db.scalars(
        select(Message).where(Message.thread_id == session_id).order_by(Message.id)
    )
    return [
        MessageOut(
            id=m.id,
            role=m.role,
            content=m.content,
            citations=m.citations,
            agent_run_id=m.agent_run_id,
            created_at=m.created_at,
            my_rating=None,
        )
        for m in rows
    ]


@router.post("/runs", status_code=202)
async def start_run(
    payload: StartInteraction,
    request: Request,
    db: SessionDep,
    principal: CurrentPrincipal,
    client: AgentClientDep,
) -> InteractionOut:
    run = await interactions.start(
        db,
        client,
        principal,
        payload.agent_id,
        payload.input,
        payload.session_id,
        registry(request),
    )
    return InteractionOut.model_validate(run)


@router.get("/runs")
async def runs(
    request: Request,
    db: SessionDep,
    principal: CurrentPrincipal,
    agent_id: str,
    session_id: str | None = None,
) -> list[InteractionOut]:
    if agent_id not in registry(request):
        raise NotFoundError("Agent not enabled")
    query = select(AgentRun).where(
        AgentRun.agent_id == agent_id, AgentRun.triggered_by == principal.email
    )
    if session_id:
        query = query.where(AgentRun.thread_id == session_id)
    result = []
    for row in await db.scalars(query.order_by(AgentRun.created_at.desc()).limit(50)):
        try:
            await registry(request)[agent_id].authorize(db, principal, row)
        except (NotFoundError, ForbiddenError):
            continue
        result.append(InteractionOut.model_validate(row))
    return result


@router.get("/runs/{run_id}")
async def get_run(
    run_id: str, request: Request, db: SessionDep, principal: CurrentPrincipal
) -> InteractionOut:
    run = await interactions.require_run(db, principal, run_id, registry(request))
    await db.commit()
    refresh: Callable[[AsyncSession, str], Awaitable[object]] = request.app.state.refresh_run
    await refresh(db, run_id)
    await db.refresh(run)
    return InteractionOut.model_validate(run)


@router.get("/runs/{run_id}/events", response_model=None)
async def events(
    run_id: str,
    request: Request,
    db: SessionDep,
    principal: CurrentPrincipal,
    after: int = Query(default=0, ge=0),
) -> dict[str, Any] | StreamingResponse:
    await interactions.require_run(db, principal, run_id, registry(request))
    await db.commit()
    refresh: Callable[[AsyncSession, str], Awaitable[object]] = request.app.state.refresh_run
    factory: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker

    async def batch(cursor: int) -> dict[str, Any]:
        async with factory() as session:
            current = await resolve_principal(
                session,
                identity_from_request(request, request.app.state.settings),
                request.app.state.settings,
            )
            await interactions.require_run(session, current, run_id, registry(request))
            await session.commit()
            await refresh(session, run_id)
            run = await interactions.require_run(session, current, run_id, registry(request))
            return await interactions.event_batch(session, run, cursor)

    if "text/event-stream" not in request.headers.get("accept", ""):
        return await batch(after)

    async def stream() -> AsyncIterator[str]:
        cursor = after
        yield ": connected\n\n"
        while not await request.is_disconnected():
            try:
                result = await batch(cursor)
            except (NotFoundError, ForbiddenError):
                yield "event: access-denied\ndata: {}\n\n"
                return
            for item in result["events"]:
                yield f"data: {json.dumps(item)}\n\n"
            cursor = result["cursor"]
            if result["terminal"]:
                yield "event: complete\ndata: {}\n\n"
                return
            yield ": heartbeat\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/runs/{run_id}/review")
async def review_state(
    run_id: str, request: Request, db: SessionDep, principal: CurrentPrincipal
) -> dict[str, Any]:
    run = await interactions.require_run(db, principal, run_id, registry(request))
    callback = registry(request)[run.agent_id].review_state
    return await callback(db, run) if callback else {"status": "unavailable"}


@router.post("/runs/{run_id}/review")
async def review(
    run_id: str,
    payload: dict[str, Any],
    request: Request,
    db: SessionDep,
    principal: CurrentPrincipal,
    deliver: DeliverFeedback,
) -> dict[str, Any]:
    run = await interactions.require_run(db, principal, run_id, registry(request))
    callback = registry(request)[run.agent_id].review
    if run.status != "succeeded" or callback is None:
        raise ConflictError("No validated result is ready for review")
    result = await callback(db, principal, run, payload)
    await db.commit()
    deliver()
    return result


@router.post("/runs/{run_id}/feedback")
async def rate(
    run_id: str,
    payload: RatingIn,
    request: Request,
    db: SessionDep,
    principal: CurrentPrincipal,
    deliver: DeliverFeedback,
) -> dict[str, bool]:
    run = await interactions.require_run(db, principal, run_id, registry(request))
    if run.status != "succeeded":
        raise ConflictError("Only completed results can be rated")
    await feedback.record(
        db,
        run=run,
        principal=principal.email,
        kind="feedback",
        name="answer_rating",
        target="result",
        value=payload.rating,
        reasons=payload.reasons,
        comment=payload.comment,
    )
    await db.commit()
    deliver()
    return {"recorded": True}


@router.get("/runs/{run_id}/tools")
async def tool_outcomes(
    run_id: str, request: Request, db: SessionDep, principal: CurrentPrincipal
) -> list[str]:
    await interactions.require_run(db, principal, run_id, registry(request))
    return list(
        await db.scalars(select(ToolOutcome.tool_call_id).where(ToolOutcome.run_id == run_id))
    )


@router.post("/runs/{run_id}/tools/{call_id}")
async def tool_result(
    run_id: str,
    call_id: str,
    payload: dict[str, Any],
    request: Request,
    db: SessionDep,
    principal: CurrentPrincipal,
) -> dict[str, Any]:
    run = await interactions.require_run(db, principal, run_id, registry(request))
    if run.status != "succeeded":
        raise ConflictError("The run has not completed")
    await db.scalar(select(AgentRun).where(AgentRun.id == run_id).with_for_update())
    await validate_tool(db, run, call_id, registry(request)[run.agent_id])
    existing = await db.get(ToolOutcome, (run_id, call_id))
    if existing:
        if existing.result.get("status") != "claimed":
            return existing.result
        existing.result = payload
    else:
        db.add(ToolOutcome(run_id=run_id, tool_call_id=call_id, result=payload))
    await db.commit()
    return payload


async def validate_tool(
    db: AsyncSession, run: AgentRun, call_id: str, app: AgentApplication
) -> None:
    history = await db.scalars(
        select(RunEvent).where(RunEvent.run_id == run.id).order_by(RunEvent.sequence)
    )
    name, arguments, complete = "", "", False
    for row in history:
        event = row.event
        if event.get("toolCallId") != call_id:
            continue
        if event["type"] == "TOOL_CALL_START":
            name = event["toolCallName"]
        elif event["type"] == "TOOL_CALL_ARGS":
            arguments += event["delta"]
        elif event["type"] == "TOOL_CALL_END":
            complete = True
    schema = app.tools.get(name)
    if schema is None or not complete:
        raise NotFoundError("Registered tool call not found")
    try:
        schema.model_validate_json(arguments)
    except ValidationError as exc:
        raise InvalidInputError("Invalid tool arguments") from exc


@router.post("/runs/{run_id}/tools/{call_id}/claim")
async def claim_tool(
    run_id: str, call_id: str, request: Request, db: SessionDep, principal: CurrentPrincipal
) -> dict[str, bool]:
    run = await interactions.require_run(db, principal, run_id, registry(request))
    await db.scalar(select(AgentRun).where(AgentRun.id == run_id).with_for_update())
    if run.status != "succeeded":
        raise ConflictError("The run has not completed")
    await validate_tool(db, run, call_id, registry(request)[run.agent_id])
    if await db.get(ToolOutcome, (run_id, call_id)):
        return {"execute": False}
    db.add(ToolOutcome(run_id=run_id, tool_call_id=call_id, result={"status": "claimed"}))
    await db.commit()
    return {"execute": True}
