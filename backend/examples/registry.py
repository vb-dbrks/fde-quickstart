"""The composition root: enable examples here and through ENABLED_EXAMPLES."""

from typing import Any

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.principal import Principal
from backend.contracts.agent_contract_v1 import AgentOutput, AgentRunRequest
from backend.contracts.examples import ChatInput, ChatResult, GenerationInput, GenerationResult
from backend.domain.errors import ConflictError, InvalidInputError
from backend.domain.models import AgentRun, GenerationArtifact, Message
from backend.services.interactions import AgentApplication


async def finish_chat(db: AsyncSession, run: AgentRun, result: dict[str, Any]) -> None:
    if run.thread_id:
        db.add(
            Message(
                thread_id=run.thread_id,
                role="assistant",
                content=result["content"],
                citations=[],
                agent_run_id=run.id,
            )
        )


async def finish_generation(db: AsyncSession, run: AgentRun, result: dict[str, Any]) -> None:
    db.add(GenerationArtifact(run_id=run.id, value=result, status="pending"))


async def review_generation(
    db: AsyncSession, principal: Principal, run: AgentRun, payload: dict[str, Any]
) -> dict[str, Any]:
    row = await db.get(GenerationArtifact, run.id, with_for_update=True)
    if row is None:
        raise ConflictError("No validated result is ready for review")
    decision = payload.get("decision")
    if decision not in ("accepted", "rejected"):
        raise ConflictError("Choose accepted or rejected")
    try:
        value = GenerationResult.model_validate(payload.get("value", row.value)).model_dump(
            mode="json"
        )
    except ValidationError as exc:
        raise InvalidInputError("The edited result does not match the result schema") from exc
    if row.status != "pending":
        if row.status != decision or (decision == "accepted" and row.value != value):
            raise ConflictError("This result has already been reviewed")
    else:
        row.status = decision
        if decision == "accepted":
            row.value = value
        from backend.services import feedback

        await feedback.record(
            db,
            run=run,
            principal=principal.email,
            kind="feedback",
            name="suggestion_accepted",
            target="result",
            value=decision == "accepted",
        )
        if decision == "accepted" and value != run.result:
            await feedback.record(
                db,
                run=run,
                principal=principal.email,
                kind="expectation",
                name="result",
                target="result",
                value=value,
            )
    return {"status": row.status, "value": row.value}


async def generation_review_state(db: AsyncSession, run: AgentRun) -> dict[str, Any]:
    row = await db.get(GenerationArtifact, run.id)
    return {"status": row.status, "value": row.value} if row else {"status": "unavailable"}


class FocusField(BaseModel):
    field_path: str = Field(pattern=r"^[a-z_]+\.[a-z_]+$")


async def document_access(db: AsyncSession, principal: Principal, run: AgentRun) -> None:
    from backend.services.agent_runs import get_run_for

    await get_run_for(db, principal, run.id)


def applications(enabled: frozenset[str]) -> dict[str, AgentApplication]:
    registered = {
        "chat": AgentApplication("chat", ChatInput, ChatResult, finalize=finish_chat),
        "generation": AgentApplication(
            "generation",
            GenerationInput,
            GenerationResult,
            finalize=finish_generation,
            review=review_generation,
            review_state=generation_review_state,
        ),
        "documents": AgentApplication(
            "documents",
            AgentRunRequest,
            AgentOutput,
            authorize=document_access,
            tools={"focus_field": FocusField},
            execution_version="v1",
        ),
    }
    return {key: value for key, value in registered.items() if value.example in enabled}
