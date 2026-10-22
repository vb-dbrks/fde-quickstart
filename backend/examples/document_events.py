"""Bridge the v1 document contract to the common durable interaction journal."""

import json

from ag_ui.core import (
    EventType,
    StateSnapshotEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.models import AgentRun
from backend.services.agent_runs import RunDeps, refresh_run
from backend.services.interactions import append_event, begin_events, end_events, event_json


async def refresh_document_events(db: AsyncSession, deps: RunDeps, run_id: str) -> AgentRun | None:
    await refresh_run(db, deps, run_id)
    run = await db.scalar(
        select(AgentRun)
        .where(AgentRun.id == run_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if run is None:
        return None
    # A terminal event is written exactly once, including when ordinary REST polling finished first.
    from backend.domain.models import RunEvent

    last = await db.get(RunEvent, (run.id, run.event_count)) if run.event_count else None
    if last and last.event["type"] in ("RUN_FINISHED", "RUN_ERROR"):
        await db.commit()
        return run
    begin_events(db, run)
    raw = run.response_payload or {}
    events = raw.get("events") or []
    for item in events[run.runtime_cursor :]:
        if item.get("type") not in ("RUN_STARTED", "RUN_FINISHED", "RUN_ERROR"):
            append_event(db, run, item)
    run.runtime_cursor = len(events)
    if run.status in ("succeeded", "failed"):
        if run.status == "succeeded":
            output = raw.get("output") or {}
            run.result = output
            append_event(
                db,
                run,
                event_json(
                    StateSnapshotEvent(
                        type=EventType.STATE_SNAPSHOT,
                        snapshot={"result": output, "provisional": False},
                    )
                ),
            )
            action = output.get("ui_action")
            if action and action.get("name") == "focus_field":
                path = action.get("field_path")
                document_type = run.request_payload.get("document_context", {}).get(
                    "document_type", ""
                )
                spec = deps.catalog.get(document_type)
                if spec and spec.field(path):
                    call_id = f"{run.id}:focus"
                    append_event(
                        db,
                        run,
                        event_json(
                            ToolCallStartEvent(
                                type=EventType.TOOL_CALL_START,
                                tool_call_id=call_id,
                                tool_call_name="focus_field",
                            )
                        ),
                    )
                    append_event(
                        db,
                        run,
                        event_json(
                            ToolCallArgsEvent(
                                type=EventType.TOOL_CALL_ARGS,
                                tool_call_id=call_id,
                                delta=json.dumps({"field_path": path}),
                            )
                        ),
                    )
                    append_event(
                        db,
                        run,
                        event_json(
                            ToolCallEndEvent(type=EventType.TOOL_CALL_END, tool_call_id=call_id)
                        ),
                    )
        end_events(db, run)
    await db.commit()
    return run
