"""Assistant threads: private conversations about a document. Messages live in Lakebase; the agent
only ever sees the history the app sends with each turn."""

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.principal import Principal
from backend.contracts.agent_contract_v1 import AgentOutput
from backend.domain.errors import NotFoundError
from backend.domain.models import AgentRun, Document, Message, Thread


async def create_thread(
    db: AsyncSession, principal: Principal, document: Document, *, title: str
) -> Thread:
    thread = Thread(
        document_id=document.id, owner=principal.email, title=title.strip()[:200] or "Conversation"
    )
    db.add(thread)
    await db.flush()
    return thread


async def list_threads(
    db: AsyncSession, principal: Principal, document_id: str
) -> Sequence[Thread]:
    query = (
        select(Thread)
        .where(Thread.document_id == document_id, Thread.owner == principal.email)
        .order_by(Thread.created_at.desc())
    )
    return (await db.scalars(query)).all()


async def require_thread(db: AsyncSession, principal: Principal, thread_id: str) -> Thread:
    thread = await db.get(Thread, thread_id)
    if thread is None or thread.owner != principal.email:
        raise NotFoundError("Conversation not found")
    return thread


async def list_messages(db: AsyncSession, thread_id: str) -> Sequence[Message]:
    query = select(Message).where(Message.thread_id == thread_id).order_by(Message.id)
    return (await db.scalars(query)).all()


async def recent_history(
    db: AsyncSession, thread_id: str, *, limit: int
) -> tuple[list[tuple[str, str]], bool]:
    """The last ``limit`` user/assistant messages, oldest first, and whether older ones exist."""
    query = (
        select(Message.role, Message.content)
        .where(Message.thread_id == thread_id, Message.role.in_(("user", "assistant")))
        .order_by(Message.id.desc())
        .limit(limit + 1)
    )
    rows = [(role, content) for role, content in await db.execute(query)]
    truncated = len(rows) > limit
    return list(reversed(rows[:limit])), truncated


async def finalize_assistant_turn(db: AsyncSession, *, run: AgentRun, output: AgentOutput) -> None:
    """Store the assistant's reply on the first ``succeeded`` poll (the user's message is stored at
    submit time)."""
    if run.materialised_at is not None or run.thread_id is None or output.answer is None:
        return
    db.add(
        Message(
            thread_id=run.thread_id,
            role="assistant",
            content=output.answer.content,
            citations=[citation.model_dump(mode="json") for citation in output.answer.citations],
            agent_run_id=run.id,
        )
    )
    run.materialised_at = datetime.now(UTC)
