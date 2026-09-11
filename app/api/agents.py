"""AI Agent 配置 API：CRUD（OpenAI 兼容接口参数）。"""
from fastapi import APIRouter, HTTPException

from app.models import AgentCreate, AgentOut, AgentUpdate
from app.services import agent_store

router = APIRouter(prefix="/api/v1/ai/agents", tags=["ai-agents"])


@router.get("")
async def list_agents():
    return {"agents": [AgentOut(**a).model_dump() for a in await agent_store.list_agents()]}


@router.post("", status_code=201)
async def create_agent(body: AgentCreate):
    if not (body.name.strip() and body.base_url.strip() and body.api_key.strip() and body.model_id.strip()):
        raise HTTPException(status_code=400, detail="name / base_url / api_key / model_id 均不能为空")
    row = await agent_store.create_agent(body.name.strip(), body.base_url.strip(), body.api_key.strip(), body.model_id.strip())
    return AgentOut(**row).model_dump()


@router.patch("/{agent_id}")
async def update_agent(agent_id: str, body: AgentUpdate):
    if await agent_store.get_agent(agent_id) is None:
        raise HTTPException(status_code=404, detail=f"Agent 不存在：{agent_id}")
    row = await agent_store.update_agent(agent_id, **body.model_dump())
    return AgentOut(**row).model_dump()


@router.delete("/{agent_id}")
async def delete_agent(agent_id: str):
    if await agent_store.get_agent(agent_id) is None:
        raise HTTPException(status_code=404, detail=f"Agent 不存在：{agent_id}")
    await agent_store.delete_agent(agent_id)
    return {"deleted": agent_id}
