"""AI 智能打标：批量取未打标收藏 → 调 OpenAI 兼容接口输出 JSON → tags 入库。

任务生命周期复用 fetch_tasks 表（action = ai_tag）：
result_count = 本轮处理的条目数，new_favorites = 成功打标的条目数。
"""
import asyncio
import json
import logging

import httpx

from app.services import agent_store, data_store
from app.utils import new_id, now_iso

logger = logging.getLogger("favapi.ai_tagging")

AI_TAG_ACTION = "ai_tag"
BATCH_SIZE = 20            # 每次请求喂给模型的标题数
DEFAULT_LIMIT = 50         # 单轮打标条目上限（防单次任务耗时/费用失控）
MAX_TAGS_PER_ITEM = 5
LLM_TIMEOUT = 120          # 单次 LLM 请求超时（秒）

SYSTEM_PROMPT = (
    "你是一名内容收藏打标助手。根据用户给出的内容标题列表，为每条内容生成 "
    f"2~{MAX_TAGS_PER_ITEM} 个简短中文标签（主题、领域、内容形式等），标签必须是通用词汇，不要包含标题原文。"
    "只输出 JSON 对象，不要输出任何其他文字或代码块标记。"
)
OUTPUT_FORMAT = {"results": [{"content_id": "原样返回输入的 content_id", "tags": ["标签1", "标签2"]}]}


class TaggingValidationError(ValueError):
    """参数 / agent 配置问题，API 层转为 400。"""


async def validate_tagging(params: dict) -> dict:
    agent = await agent_store.get_agent((params or {}).get("agent_id") or "")
    if agent is None:
        raise TaggingValidationError("无效的 agent_id：请先在 AI Agent 配置中创建")
    return agent


async def start_tagging(platform: str, params: dict, async_run: bool = False) -> dict:
    """创建打标任务并执行；async_run=true 立即返回 pending 任务。"""
    params = params or {}
    agent = await validate_tagging(params)

    task_id = new_id("task")
    await data_store.create_task(task_id, "", platform or "", AI_TAG_ACTION, params)

    if async_run:
        asyncio.create_task(_guarded_run(task_id, agent, platform, params))
        return {"task_id": task_id, "status": "pending", "task_url": f"/api/v1/tasks/{task_id}"}
    return await _run_tagging_task(task_id, agent, platform, params)


async def _guarded_run(task_id: str, agent: dict, platform: str, params: dict):
    try:
        await _run_tagging_task(task_id, agent, platform, params)
    except Exception:
        logger.exception("后台打标任务 %s 异常", task_id)


async def _run_tagging_task(task_id: str, agent: dict, platform: str, params: dict) -> dict:
    limit = max(1, min(int(params.get("limit") or DEFAULT_LIMIT), 2000))
    await data_store.update_task(task_id, status="running", started_at=now_iso())

    processed = tagged = 0
    try:
        while processed < limit:
            size = min(BATCH_SIZE, limit - processed)
            items = await _pending_contents(platform, size)
            if not items:
                break
            results = await _tag_batch(agent, items)
            tagged += await _save_tags(results)
            # 模型漏掉的条目写空数组（NULL=未打标，[]=已尝试无标签），避免反复重试
            missing = [it["content_id"] for it in items if it["content_id"] not in {r["content_id"] for r in results}]
            if missing:
                await _save_tags([{"content_id": cid, "tags": []} for cid in missing])
            processed += len(items)
        payload = {
            "task_id": task_id,
            "action": AI_TAG_ACTION,
            "status": "success",
            "result_count": processed,
            "new_favorites": tagged,  # 列复用：成功打标条数
        }
        await data_store.update_task(
            task_id, status="success", result_count=processed, new_favorites=tagged, finished_at=now_iso()
        )
        logger.info("打标任务 %s 完成：处理 %s 条，打标 %s 条", task_id, processed, tagged)
        return payload
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception("打标任务 %s 失败", task_id)
        message = str(exc)[:2000]
        await data_store.update_task(
            task_id, status="failed", error_message=message, finished_at=now_iso()
        )
        return {
            "task_id": task_id, "action": AI_TAG_ACTION, "status": "failed",
            "result_count": processed, "new_favorites": tagged, "error_message": message,
        }


async def _pending_contents(platform: str, limit: int) -> list[dict]:
    where, params = "tags IS NULL", []
    if platform:
        where += " AND platform = ?"
        params.append(platform)
    return await data_store.db.query_all(
        f"""SELECT content_id, platform, title FROM contents
            WHERE {where} AND title IS NOT NULL AND title != ''
            ORDER BY last_seen_at DESC LIMIT ?""",
        (*params, limit),
    )


async def _tag_batch(agent: dict, items: list[dict]) -> list[dict]:
    """一次请求喂多个标题，返回 [{content_id, tags}]。"""
    payload = {
        "model": agent["model_id"],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"请为以下 {len(items)} 条内容打标。\n"
                    f"输出 JSON 格式：{json.dumps(OUTPUT_FORMAT, ensure_ascii=False)}\n"
                    f"items：{json.dumps([{'content_id': it['content_id'], 'title': it['title']} for it in items], ensure_ascii=False)}"
                ),
            },
        ],
    }
    body = await _chat_completions(agent, payload)
    return _parse_results(body, {it["content_id"] for it in items})


async def _chat_completions(agent: dict, payload: dict) -> dict:
    url = f"{agent['base_url']}/chat/completions"
    headers = {"Authorization": f"Bearer {agent['api_key']}"}
    async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code == 400 and "response_format" in resp.text:
            # 部分兼容网关不支持 response_format，降级为纯 prompt 约束重试
            fallback = {k: v for k, v in payload.items() if k != "response_format"}
            resp = await client.post(url, json=fallback, headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(f"LLM 接口返回 {resp.status_code}：{resp.text[:300]}")
        return resp.json()


def _parse_results(body: dict, valid_ids: set[str]) -> list[dict]:
    content = ""
    for choice in body.get("choices") or []:
        message = choice.get("message") or {}
        content = message.get("content") or ""
        if content:
            break
    if not content:
        raise RuntimeError("LLM 返回内容为空")

    text = content.strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise RuntimeError(f"LLM 未返回 JSON：{text[:200]}")
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"LLM 返回的 JSON 解析失败：{exc}；原文：{text[:200]}")

    results = data.get("results") if isinstance(data, dict) else data
    if not isinstance(results, list):
        raise RuntimeError(f"LLM 返回结构不符（缺少 results 数组）：{text[:200]}")

    out = []
    for r in results:
        cid = (r or {}).get("content_id")
        tags = (r or {}).get("tags")
        if cid in valid_ids and isinstance(tags, list) and tags:
            cleaned = [str(t).strip().lstrip("#") for t in tags if str(t).strip()]
            if cleaned:
                out.append({"content_id": cid, "tags": cleaned[:MAX_TAGS_PER_ITEM]})
    return out


async def _save_tags(results: list[dict]) -> int:
    now = now_iso()
    for r in results:
        await data_store.db.execute(
            "UPDATE contents SET tags = ?, tagged_at = ? WHERE content_id = ?",
            (json.dumps(r["tags"], ensure_ascii=False), now, r["content_id"]),
        )
    return len(results)
