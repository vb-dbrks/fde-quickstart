"""Users' feedback on what the agent wrote. Stored here, then on the run's MLflow trace."""

from fastapi import APIRouter, status

from backend.api.deps import DeliverFeedback, SessionDep
from backend.api.presenters import rating_out
from backend.auth.access import require_document
from backend.auth.deps import CurrentPrincipal
from backend.domain.enums import Access, RunStatus
from backend.domain.errors import ConflictError
from backend.domain.models import FieldProposal
from backend.domain.schemas import RatingIn, RatingOut
from backend.services import agent_runs, feedback

router = APIRouter(tags=["feedback"])


@router.put("/documents/{document_id}/fields/{field_path}/rating")
async def rate_field(
    document_id: str,
    field_path: str,
    payload: RatingIn,
    principal: CurrentPrincipal,
    db: SessionDep,
    deliver_feedback: DeliverFeedback,
) -> RatingOut:
    """Rate the value the agent wrote for a field. Rating again replaces your earlier rating."""
    document, _ = await require_document(db, principal, document_id, Access.VIEW)
    row = await feedback.rate_field(
        db,
        principal,
        document,
        field_path,
        rating=payload.rating,
        reasons=payload.reasons,
        comment=payload.comment,
    )
    await db.commit()
    deliver_feedback()
    out = rating_out(row)
    assert out is not None
    return out


@router.put("/messages/{message_id}/rating")
async def rate_answer(
    message_id: int,
    payload: RatingIn,
    principal: CurrentPrincipal,
    db: SessionDep,
    deliver_feedback: DeliverFeedback,
) -> RatingOut:
    """Rate an assistant answer in one of your conversations."""
    row, _ = await feedback.rate_answer(
        db,
        principal,
        message_id,
        rating=payload.rating,
        reasons=payload.reasons,
        comment=payload.comment,
    )
    await db.commit()
    deliver_feedback()
    out = rating_out(row)
    assert out is not None
    return out


@router.post("/agent-runs/{run_id}/dismiss", status_code=status.HTTP_204_NO_CONTENT)
async def dismiss_suggestion(
    run_id: str, principal: CurrentPrincipal, db: SessionDep, deliver_feedback: DeliverFeedback
) -> None:
    """Dismiss an enhance_field suggestion: the agent's revision was not wanted."""
    run, document = await agent_runs.get_run_for(db, principal, run_id)
    field_path = ((run.request_payload or {}).get("enhance_context") or {}).get("field_path")
    if run.run_kind != "enhance_field" or run.status != RunStatus.SUCCEEDED or not field_path:
        raise ConflictError("Only a finished suggestion can be dismissed")
    if run.review_required:
        await require_document(db, principal, document.id, Access.EDIT, for_update=True)
        proposal = await db.get(FieldProposal, (run.id, field_path), with_for_update=True)
        if proposal is None or proposal.status == "accepted":
            raise ConflictError("This proposal cannot be rejected")
        proposal.status = "rejected"
    await feedback.record_verdict(db, principal, run, field_path, accepted=False)
    await db.commit()
    deliver_feedback()
