import logging
from typing import Annotated

import openai
from fastapi import APIRouter, Depends, HTTPException, status

from app.agents.base import AgentContext, AgentNotConfiguredError
from app.deps import AgentRegistryDep, SessionmakerDep
from app.permissions.deps import CurrentPrincipal, require
from app.permissions.roles import Permission
from app.permissions.service import Principal
from app.schemas import AgentInfo, AgentInvokeIn, AgentInvokeOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])

Invoker = Annotated[Principal, Depends(require(Permission.AGENTS_INVOKE))]


@router.get("")
def list_agents(_: CurrentPrincipal, registry: AgentRegistryDep) -> list[AgentInfo]:
    return [
        AgentInfo(name=agent.name, description=agent.description, configured=agent.configured)
        for agent in registry.all()
    ]


@router.post("/{name}/invoke")
async def invoke_agent(
    name: str,
    payload: AgentInvokeIn,
    principal: Invoker,
    registry: AgentRegistryDep,
    sessions: SessionmakerDep,
) -> AgentInvokeOut:
    """Run an agent to completion. Replies must arrive within the Apps proxy's 120 s limit."""
    agent = registry.get(name)
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown agent: {name}")
    try:
        reply = await agent.run(
            AgentContext(principal=principal, sessions=sessions), payload.message
        )
    except AgentNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except openai.APIError as exc:
        logger.exception("Agent %s failed calling the model endpoint", name)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "The model endpoint returned an error."
        ) from exc
    return AgentInvokeOut(agent=name, output=reply.output)
