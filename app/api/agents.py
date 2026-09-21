"""AI Agent 配置 API：CRUD（OpenAI 兼容接口参数）+ 连通性测试。"""
from fastapi import APIRouter, HTTPException

from app.models import AgentCreate, AgentOut, AgentUpdate
from app.services import agent_store
from app.services.ai_tagging import test_agent

router = APIRouter(prefix="/api/v1/ai/agents", tags=["ai-agents"])


@router.get("")
async def list_agents():
    return {"agents": [AgentOut(**a).model_dump() for a in await agent_store.list_agents()]}


@router.post("", status_code=201)
async def create_agent(body: AgentCreate):
    is_jev = body.provider == "jev"
    if not (body.name.strip() and body.api_key.strip()):
        raise HTTPException(status_code=400, detail="name / api_key 不能为空")
    if not is_jev and not (body.base_url.strip() and body.model_id.strip()):
        raise HTTPException(status_code=400, detail="OpenAI 兼容方式必须填写 base_url / model_id")
    row = await agent_store.create_agent(
        body.name.strip(), body.base_url.strip(), body.api_key.strip(),
        body.model_id.strip(), body.provider,
    )
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


@router.post("/{agent_id}/test")
async def test_agent_conn(agent_id: str):
    """连通性测试：用最小 chat 请求验证配置，失败时 ok=false 携带错误详情。"""
    agent = await agent_store.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent 不存在：{agent_id}")
    return await test_agent(agent)
