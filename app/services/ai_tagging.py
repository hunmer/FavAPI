"""AI 智能打标：批量取未打标收藏 → 调 OpenAI 兼容接口输出 JSON → tags 入库。

任务生命周期复用 fetch_tasks 表（action = ai_tag）：
result_count = 本轮处理的条目数，new_favorites = 成功打标的条目数。
"""
import asyncio
import json
import logging
import time

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
    f"2~{MAX_TAGS_PER_ITEM} 个简短中文标签。"
    "优先从用户提供的标签池中选择已有标签，保持标签体系统一、避免衍生杂乱同义标签；"
    "仅当内容明确不属于标签池中的任何标签时，才新建一个简短、通用的中文标签（主题、领域、内容形式）。"
    "标签必须是通用词汇，不要包含标题原文。"
    "只输出 JSON 对象，不要输出任何其他文字或代码块标记。"
)
OUTPUT_FORMAT = {"results": [{"content_id": "原样返回输入的 content_id", "tags": ["标签1", "标签2"]}]}

# 标签池中「库中已有标签」最多取多少个（按引用数倒序，防 prompt 过长）
MAX_EXISTING_TAGS_IN_POOL = 120


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


def _resolve_limit(params: dict) -> int:
    return max(1, min(int((params or {}).get("limit") or DEFAULT_LIMIT), 2000))


async def _run_tagging_task(task_id: str, agent: dict, platform: str, params: dict) -> dict:
    limit = _resolve_limit(params)
    await data_store.update_task(task_id, status="running", started_at=now_iso())

    processed = tagged = 0
    try:
        async for items, results in _tagging_batches(agent, platform, limit):
            processed += len(items)
            tagged += len(results)
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


async def _tagging_batches(agent: dict, platform: str, limit: int):
    """逐批产出 (items, results)；无待打标内容时结束。"""
    processed = 0
    batch_no = 0
    while processed < limit:
        size = min(BATCH_SIZE, limit - processed)
        items = await _pending_contents(platform, size)
        if not items:
            if batch_no == 0:
                logger.info("打标：平台=%s 无待打标内容", platform or "全部")
            break
        batch_no += 1
        started = time.monotonic()
        logger.info(
            "打标批次 #%s 开始：平台=%s 取 %s 条（累计 %s/%s），model=%s",
            batch_no, platform or "全部", len(items), processed, limit, agent["model_id"],
        )
        try:
            results = await _tag_batch(agent, items)
        except Exception as exc:
            logger.error("打标批次 #%s LLM 调用失败（%s 条丢弃，任务中止）：%s",
                         batch_no, len(items), str(exc)[:300])
            raise
        elapsed = time.monotonic() - started
        await _save_tags(results)
        # 模型漏掉的条目写空数组（NULL=未打标，[]=已尝试无标签），避免反复重试
        got_ids = {r["content_id"] for r in results}
        missing = [it["content_id"] for it in items if it["content_id"] not in got_ids]
        if missing:
            await _save_tags([{"content_id": cid, "tags": []} for cid in missing])
        processed += len(items)
        logger.info(
            "打标批次 #%s 完成：LLM %.1fs，有效 %s 条，漏标 %s 条，样例=%s",
            batch_no, elapsed, len(results), len(missing),
            json.dumps(results[0]["tags"], ensure_ascii=False) if results else "无",
        )
        yield items, results


async def stream_tagging_events(agent: dict, platform: str, params: dict):
    """SSE 流式打标：逐批推送进度，结束推 done/error。

    消费方（API 层）断开时 generator 被 close，worker 中止并把任务标记为失败
    （已入库的批次结果保留）。
    """
    limit = _resolve_limit(params)
    task_id = new_id("task")
    await data_store.create_task(task_id, "", platform or "", AI_TAG_ACTION, params or {})
    yield {"type": "task", "task_id": task_id, "limit": limit}

    finished = False
    try:
        await data_store.update_task(task_id, status="running", started_at=now_iso())
        processed = tagged = 0
        title_by_id: dict[str, str] = {}
        async for items, results in _tagging_batches(agent, platform, limit):
            processed += len(items)
            tagged += len(results)
            title_by_id.update({it["content_id"]: it["title"] for it in items})
            yield {
                "type": "batch",
                "processed": processed,
                "tagged": tagged,
                "items": [
                    {"content_id": r["content_id"], "title": title_by_id.get(r["content_id"], ""),
                     "tags": r["tags"]}
                    for r in results
                ],
            }
        await data_store.update_task(
            task_id, status="success", result_count=processed, new_favorites=tagged, finished_at=now_iso()
        )
        finished = True
        yield {"type": "done", "task_id": task_id, "processed": processed, "tagged": tagged}
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception("流式打标任务 %s 失败", task_id)
        await data_store.update_task(
            task_id, status="failed", error_message=str(exc)[:2000], finished_at=now_iso()
        )
        finished = True
        yield {"type": "error", "task_id": task_id, "error_message": str(exc)[:2000]}
    finally:
        if not finished:
            # 客户端断开：generator 被 close 走到这里，中止后续批次
            logger.warning("流式打标任务 %s 因客户端断开中止", task_id)
            await data_store.update_task(
                task_id, status="failed", error_message="客户端断开，打标中止", finished_at=now_iso()
            )


async def _pending_contents(platform: str, limit: int) -> list[dict]:
    where, params = "tags IS NULL", []
    if platform:
        where += " AND platform = ?"
        params.append(platform)
    return await data_store.db.query_all(
        f"""SELECT content_id, platform, title FROM contents
            WHERE {where} AND title IS NOT NULL AND title != ''
            ORDER BY rowid DESC LIMIT ?""",
        (*params, limit),
    )


async def _label_pool() -> str:
    """标签池文案：内置分组 + 库中已有标签（按引用数取 top N）。

    每批打标前重新构建，已打出的新标签会进入后续批次的池，促使标签自我收敛。
    """
    from app.taxonomy import BUILTIN_TAG_GROUPS, builtin_tags

    parts = [f"{group}：{'、'.join(tags)}" for group, tags in BUILTIN_TAG_GROUPS]
    builtin = builtin_tags()
    stats = await data_store.list_tag_stats(MAX_EXISTING_TAGS_IN_POOL)
    existing = [s["tag"] for s in stats if s["tag"] not in builtin]
    if existing:
        parts.append(f"库中已有：{'、'.join(existing)}")
    return "\n".join(parts)


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
                    f"可选标签池（优先复用）：\n{await _label_pool()}\n"
                    f"输出 JSON 格式：{json.dumps(OUTPUT_FORMAT, ensure_ascii=False)}\n"
                    f"items：{json.dumps([{'content_id': it['content_id'], 'title': it['title']} for it in items], ensure_ascii=False)}"
                ),
            },
        ],
    }
    body = await _chat_completions(agent, payload)
    logger.debug("打标 LLM 原始响应：%s", json.dumps(body, ensure_ascii=False)[:500])
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


async def test_agent(agent: dict) -> dict:
    """连通性测试：发送最小 chat 请求验证 base_url / api_key / model_id。"""
    import time

    payload = {"model": agent["model_id"], "messages": [{"role": "user", "content": "请直接回复：OK"}]}
    start = time.monotonic()
    try:
        body = await _chat_completions(agent, payload)
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}
    reply = ""
    for choice in body.get("choices") or []:
        reply = ((choice.get("message") or {}).get("content") or "").strip()
        if reply:
            break
    return {"ok": True, "latency_ms": round((time.monotonic() - start) * 1000), "reply": reply[:50]}


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
    dropped = 0
    for r in results:
        cid = (r or {}).get("content_id")
        tags = (r or {}).get("tags")
        if cid in valid_ids and isinstance(tags, list) and tags:
            cleaned = [str(t).strip().lstrip("#") for t in tags if str(t).strip()]
            if cleaned:
                out.append({"content_id": cid, "tags": cleaned[:MAX_TAGS_PER_ITEM]})
                continue
        dropped += 1
    if dropped:
        logger.debug("打标解析丢弃 %s 条（content_id 不匹配或 tags 无效）", dropped)
    return out


async def _save_tags(results: list[dict]) -> int:
    now = now_iso()
    for r in results:
        await data_store.db.execute(
            "UPDATE contents SET tags = ?, tagged_at = ? WHERE content_id = ?",
            (json.dumps(r["tags"], ensure_ascii=False), now, r["content_id"]),
        )
    return len(results)
