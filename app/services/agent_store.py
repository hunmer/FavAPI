"""AI Agent 配置（OpenAI 兼容接口 / TypeSafe Jev 判定式打标）的持久化。"""
from app.database import db
from app.utils import new_id, now_iso

DEFAULT_BASE_URLS = {"openai": "", "jev": "https://api.typesafe.ai"}


def _normalize_provider(provider: str | None) -> str:
    return provider if provider in DEFAULT_BASE_URLS else "openai"


async def list_agents() -> list[dict]:
    return await db.query_all("SELECT * FROM ai_agents ORDER BY created_at ASC")


async def get_agent(agent_id: str) -> dict | None:
    return await db.query_one("SELECT * FROM ai_agents WHERE agent_id = ?", (agent_id,))


async def create_agent(name: str, base_url: str, api_key: str, model_id: str, provider: str = "openai") -> dict:
    provider = _normalize_provider(provider)
    base_url = (base_url or DEFAULT_BASE_URLS[provider]).rstrip("/")
    row = {
        "agent_id": new_id("agent"),
        "name": name,
        "base_url": base_url,
        "api_key": api_key,
        "model_id": model_id,
        "provider": provider,
        "created_at": now_iso(),
    }
    await db.execute(
        """INSERT INTO ai_agents (agent_id, name, base_url, api_key, model_id, provider, created_at)
           VALUES (:agent_id, :name, :base_url, :api_key, :model_id, :provider, :created_at)""",
        row,
    )
    return row


async def update_agent(agent_id: str, **fields) -> dict | None:
    values = {k: v for k, v in fields.items() if v is not None and k in ("name", "base_url", "api_key", "model_id", "provider")}
    if "provider" in values:
        values["provider"] = _normalize_provider(values["provider"])
    if "base_url" in values:
        values["base_url"] = values["base_url"].rstrip("/")
    if values:
        cols = ", ".join(f"{k} = ?" for k in values)
        await db.execute(f"UPDATE ai_agents SET {cols} WHERE agent_id = ?", (*values.values(), agent_id))
    return await get_agent(agent_id)


async def delete_agent(agent_id: str) -> bool:
    cur = await db.execute("DELETE FROM ai_agents WHERE agent_id = ?", (agent_id,))
    return cur.rowcount > 0
