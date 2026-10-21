from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status

from backend.api.deps import AgentClientDep, CatalogDep, NotifierDep, SessionDep, SettingsDep
from backend.api.presenters import run_out
from backend.auth.access import require_document
from backend.auth.deps import CurrentPrincipal
from backend.domain.enums import RunStatus
from backend.domain.schemas import AgentRunCreate, AgentRunOut
from backend.services import agent_runs
from backend.services.agent_runs import RunDeps, RunOptions

router = APIRouter(tags=["agent runs"])


def get_run_deps(
    client: AgentClientDep, catalog: CatalogDep, settings: SettingsDep, notifier: NotifierDep
) -> RunDeps:
    return RunDeps(client=client, catalog=catalog, settings=settings, notifier=notifier)


RunDepsDep = Annotated[RunDeps, Depends(get_run_deps)]


@router.post("/documents/{document_id}/agent-runs", status_code=status.HTTP_202_ACCEPTED)
async def start_run(
    document_id: str,
    payload: AgentRunCreate,
    principal: CurrentPrincipal,
    db: SessionDep,
    deps: RunDepsDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> AgentRunOut:
    """Start an agent run. Poll ``GET /api/agent-runs/{id}`` until it succeeds or fails."""
    document, access = await require_document(db, principal, document_id)
    run = await agent_runs.start_run(
        db,
        deps,
        principal,
        document,
        access,
        RunOptions(
            run_kind=payload.run_kind,
            instruction=payload.instruction,
            scope=payload.scope,
            field_path=payload.field_path,
            thread_id=payload.thread_id,
            message=payload.message,
            source_document_ids=payload.source_document_ids,
        ),
        idempotency_key=idempotency_key,
    )
    return run_out(run)


@router.get("/agent-runs/{run_id}")
async def get_run(
    run_id: str, principal: CurrentPrincipal, db: SessionDep, deps: RunDepsDep, request: Request
) -> AgentRunOut:
    """Latest state of a run. While it is in progress this refreshes it from the agent (lazy
    refresh); when it first succeeds the output is materialised in the same transaction."""
    run, _ = await agent_runs.get_run_for(db, principal, run_id)
    if not RunStatus(run.status).terminal:
        await db.commit()  # release the read before refresh_run locks the row
        refreshed = await agent_runs.refresh_run(db, deps, run_id)
        run = refreshed or run
    return run_out(run)


@router.get("/documents/{document_id}/agent-runs")
async def list_runs(
    document_id: str, principal: CurrentPrincipal, db: SessionDep
) -> list[AgentRunOut]:
    document, _ = await require_document(db, principal, document_id)
    return [run_out(run) for run in await agent_runs.recent_runs(db, principal, document.id)]
