"""AI 智能打标：批量取未打标收藏 → 调模型输出标签 → tags 入库。

两种打标方式（agent.provider）：
- openai（默认）：批量标题喂 OpenAI 兼容 chat 接口，自由生成标签；
- jev：TypeSafe System One（Jev 模型）判定式两阶段 —— choice 召回内容分组 →
  noul 逐标签判定概率，标签空间完全由库内 tag_groups 分组体系控制，不产生新标签。

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

# Jev（TypeSafe System One）打标参数
JEV_DEFAULT_MODEL = "jev-latest"
JEV_GROUP_THRESHOLD = 0.65  # 分组召回阈值：choice probabilities 达标的分组全部进入第二阶段
JEV_TAG_THRESHOLD = 0.50    # 标签保留阈值：noul 概率达标才打标
JEV_ITEM_CONCURRENCY = 4    # 批内单条内容并发判定数
JEV_RETRIES = 2             # 限流/网关瞬时错误（429/502/503/504/529）指数退避重试次数

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
    """limit=0 表示不限制（处理全部待打标内容）；未传时默认 DEFAULT_LIMIT。"""
    raw = (params or {}).get("limit")
    if raw is None or raw == "":
        return DEFAULT_LIMIT
    return max(0, min(int(raw), 2000))


def _resolve_include_no_match(params: dict) -> bool:
    """打标范围：true 时「已打标但无命中」（空标签数组）的内容也纳入重打。"""
    return bool((params or {}).get("include_no_match"))


async def _run_tagging_task(task_id: str, agent: dict, platform: str, params: dict) -> dict:
    limit = _resolve_limit(params)
    include_no_match = _resolve_include_no_match(params)
    await data_store.update_task(task_id, status="running", started_at=now_iso())

    processed = tagged = 0
    try:
        async for item in _tagging_stream(agent, platform, limit, include_no_match):
            processed += 1
            if item["tags"]:
                tagged += 1
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


async def _tagging_stream(agent: dict, platform: str, limit: int, include_no_match: bool = False):
    """逐条产出打标结果 {content_id, title, tags}；无待打标内容时结束。

    jev：批内逐条两阶段判定（并发受 JEV_ITEM_CONCURRENCY 限制），先完成先写库先产出；
    openai：整批一次请求，结果逐条产出（模型漏掉的条目 tags=[]）。
    """
    processed = 0
    batch_no = 0
    while limit <= 0 or processed < limit:  # limit=0：不限制，直到无待打标内容
        size = BATCH_SIZE if limit <= 0 else min(BATCH_SIZE, limit - processed)
        items = await _pending_contents(platform, size, include_no_match)
        if not items:
            if batch_no == 0:
                logger.info("打标：平台=%s 无待打标内容", platform or "全部")
            break
        batch_no += 1
        started = time.monotonic()
        logger.info(
            "打标批次 #%s 开始：平台=%s 取 %s 条（累计 %s/%s），方式=%s，model=%s",
            batch_no, platform or "全部", len(items), processed, limit,
            agent.get("provider") or "openai", agent.get("model_id") or "-",
        )
        if agent.get("provider") == "jev":
            async for r in _tag_batch_jev_stream(agent, items):
                await _save_tags([r])
                processed += 1
                title = next((it["title"] for it in items if it["content_id"] == r["content_id"]), "")
                yield {"content_id": r["content_id"], "title": title, "tags": r["tags"]}
        else:
            try:
                results = await _tag_batch(agent, items)
            except Exception as exc:
                logger.error("打标批次 #%s LLM 调用失败（%s 条丢弃，任务中止）：%s",
                             batch_no, len(items), str(exc)[:300])
                raise
            await _save_tags(results)
            # 模型漏掉的条目写空数组（NULL=未打标，[]=已尝试无标签），避免反复重试
            got_ids = {r["content_id"] for r in results}
            missing = [it["content_id"] for it in items if it["content_id"] not in got_ids]
            if missing:
                await _save_tags([{"content_id": cid, "tags": []} for cid in missing])
            tags_by_id = {r["content_id"]: r["tags"] for r in results}
            processed += len(items)
            for it in items:
                yield {"content_id": it["content_id"], "title": it["title"],
                       "tags": tags_by_id.get(it["content_id"], [])}
        elapsed = time.monotonic() - started
        logger.info("打标批次 #%s 完成：%.1fs，共 %s 条", batch_no, elapsed, len(items))


async def stream_tagging_events(agent: dict, platform: str, params: dict):
    """SSE 流式打标：逐条推送 item 进度，结束推 done/error。

    消费方（API 层）断开时 generator 被 close，worker 中止并把任务标记为失败
    （已入库的条目结果保留）。
    """
    limit = _resolve_limit(params)
    include_no_match = _resolve_include_no_match(params)
    task_id = new_id("task")
    await data_store.create_task(task_id, "", platform or "", AI_TAG_ACTION, params or {})
    yield {"type": "task", "task_id": task_id, "limit": limit}

    finished = False
    try:
        await data_store.update_task(task_id, status="running", started_at=now_iso())
        processed = tagged = 0
        async for item in _tagging_stream(agent, platform, limit, include_no_match):
            processed += 1
            if item["tags"]:
                tagged += 1
            yield {
                "type": "item",
                "processed": processed,
                "tagged": tagged,
                "content_id": item["content_id"],
                "title": item["title"],
                "tags": item["tags"],
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


async def _pending_contents(platform: str, limit: int, include_no_match: bool = False) -> list[dict]:
    """待打标内容：默认仅 tags IS NULL；include_no_match 时也纳入「已打标但无命中」（空标签数组）重打。"""
    where = "(tags IS NULL OR json_array_length(tags) = 0)" if include_no_match else "tags IS NULL"
    params: list = []
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
    """一次请求喂多个标题，返回 [{content_id, tags}]（openai 兼容方式）。"""
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


# ---------- TypeSafe Jev 判定式打标（两阶段：choice 召回分组 → noul 判定标签） ----------

async def _jev_decisions(agent: dict, state: dict, questions: dict) -> dict:
    """POST /v1/systemone，返回 answers；HTTP 错误抛异常。

    429/529（限流/过载）与 502/503/504（网关瞬时错误）按官方建议指数退避重试。
    """
    url = f"{agent.get('base_url') or agent_store.DEFAULT_BASE_URLS['jev']}/v1/systemone"
    payload = {
        "state": state,
        "model": agent.get("model_id") or JEV_DEFAULT_MODEL,
        "questions": questions,
    }
    headers = {"Authorization": f"Bearer {agent['api_key']}"}
    async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
        for attempt in range(JEV_RETRIES + 1):
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code not in (429, 502, 503, 504, 529) or attempt == JEV_RETRIES:
                break
            await asyncio.sleep(1.5 * (2 ** attempt))
    if resp.status_code != 200:
        raise RuntimeError(f"TypeSafe 接口返回 {resp.status_code}：{resp.text[:300]}")
    body = resp.json()
    answers = body.get("answers")
    if not isinstance(answers, dict) or not answers:
        raise RuntimeError(f"TypeSafe 返回结构不符（缺少 answers）：{json.dumps(body, ensure_ascii=False)[:200]}")
    return answers


async def _jev_tag_item(agent: dict, item: dict, groups: dict[str, list[str]]) -> dict:
    """单条内容两阶段打标：choice 召回分组（probabilities 软多选）→ noul 判定候选标签。"""
    state = {"title": item["title"], "platform": item.get("platform") or ""}

    # 阶段一：分组召回
    answers = await _jev_decisions(agent, state, {
        "group": {
            "type": "choice",
            "instructions": "根据标题的核心主题选择这条内容所属的内容分组，不要依据标题中偶然提到的词",
            "criteria": {g: "、".join(tags[:6]) for g, tags in groups.items()},
        }
    })
    probs = (answers.get("group") or {}).get("probabilities") or {}
    picked = [g for g, p in probs.items() if g in groups and p >= JEV_GROUP_THRESHOLD]
    if not picked and probs:  # 全部低于阈值时至少保留 top1
        top = max(probs.items(), key=lambda kv: kv[1])
        if top[0] in groups:
            picked = [top[0]]
    if not picked:
        return {"content_id": item["content_id"], "tags": []}

    # 阶段二：候选标签 noul 逐个判定（一次请求多题）
    candidates: list[str] = []
    for g in picked:
        candidates.extend(t for t in groups[g] if t not in candidates)
    questions = {
        f"tag_{i}": {
            "type": "noul",
            "instructions": f"这条内容是否明确属于「{t}」主题？（依据标题核心主题判断，勉强相关视为否）",
        }
        for i, t in enumerate(candidates)
    }
    answers = await _jev_decisions(agent, state, questions)
    scored = sorted(
        ((t, (answers.get(f"tag_{i}") or {}).get("noul") or 0.0) for i, t in enumerate(candidates)),
        key=lambda x: -x[1],
    )
    tags = [t for t, p in scored if p >= JEV_TAG_THRESHOLD][:MAX_TAGS_PER_ITEM]
    logger.debug(
        "Jev 打标 %s：分组=%s，候选=%s，命中=%s",
        item["content_id"], picked, candidates,
        [f"{t}:{p:.2f}" for t, p in scored[:MAX_TAGS_PER_ITEM]],
    )
    return {"content_id": item["content_id"], "tags": tags}


async def _tag_batch_jev_stream(agent: dict, items: list[dict]):
    """Jev 批内逐条两阶段判定，先完成先产出（供 SSE 逐条实时推送）。

    消费方提前退出（SSE 断开）或异常时，取消仍在挂起的判定任务。
    """
    from app.services import tag_store

    groups = {g["group"]: g["tags"] for g in await tag_store.list_groups() if g["tags"]}
    if not groups:
        raise RuntimeError("标签分组为空：请先在标签管理中配置分组")

    sem = asyncio.Semaphore(JEV_ITEM_CONCURRENCY)

    async def run(item: dict) -> dict:
        async with sem:
            return await _jev_tag_item(agent, item, groups)

    tasks = [asyncio.create_task(run(it)) for it in items]
    try:
        for fut in asyncio.as_completed(tasks):
            yield await fut
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()


# ---------- 智能创建标签（关键词 → AI 联想分组与标签，仅 OpenAI 兼容方式） ----------

SUGGEST_SYSTEM_PROMPT = (
    "你是一名内容收藏标签体系设计师。根据用户给出的关键词，联想生成相关的标签分组建议。"
    "生成 1~3 个相关分组，每个分组包含一个简短中文分组名和 4~8 个简短、通用的中文标签（主题词，不含标点和 #）。"
    "分组名不要与现有分组名重复；标签尽量避免与现有标签重复。"
    "只输出 JSON 对象，不要输出任何其他文字或代码块标记，格式："
    '{"groups": [{"name": "分组名", "tags": ["标签1", "标签2"]}]}'
)

SUGGEST_REFINE_PROMPT = (
    "优化要求：{instruction}\n\n"
    "请基于之前的建议调整（可增删分组、修改分组名与标签），"
    "输出调整后的完整结果，格式与之前相同：只输出 JSON 对象。"
)

# 内存会话（智能创建的多轮优化上下文）：session_id -> {"messages": [...], "expires_at": float}
# 进程重启即失效；TTL 过期 / 超上限淘汰
_SUGGEST_SESSIONS: dict[str, dict] = {}
SUGGEST_SESSION_TTL = 30 * 60
SUGGEST_SESSION_MAX = 50


def _cleanup_suggest_sessions() -> None:
    now = time.time()
    for sid in [k for k, v in _SUGGEST_SESSIONS.items() if v["expires_at"] < now]:
        _SUGGEST_SESSIONS.pop(sid, None)
    while len(_SUGGEST_SESSIONS) > SUGGEST_SESSION_MAX:
        _SUGGEST_SESSIONS.pop(next(iter(_SUGGEST_SESSIONS)))


def _extract_json_object(content: str) -> dict:
    text = content.strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise RuntimeError(f"AI 未返回 JSON：{text[:200]}")
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"AI 返回的 JSON 解析失败：{exc}；原文：{text[:200]}")
    if not isinstance(data, dict):
        raise RuntimeError(f"AI 返回结构不符（非 JSON 对象）：{text[:200]}")
    return data


async def suggest_groups(
    agent: dict, keyword: str, existing_groups: list[dict],
    session_id: str | None = None, instruction: str | None = None,
) -> tuple[list[dict], str]:
    """关键词 → AI 联想分组+标签建议；返回 ([{name, tags}], session_id)。

    带 session_id + instruction 时为「继续优化」：从内存会话的对话历史继续，
    AI 基于上一版建议按指令调整。已过滤空值与库中已有标签。
    仅支持 OpenAI 兼容方式：Jev 为判定式模型，只能从给定候选中选择，不能生成新标签。
    """
    if agent.get("provider") == "jev":
        raise TaggingValidationError("智能创建标签仅支持 OpenAI 兼容方式的 Agent（Jev 为判定式模型）")

    _cleanup_suggest_sessions()
    refine = bool(session_id and instruction)
    if refine:
        sess = _SUGGEST_SESSIONS.get(session_id)
        if sess is None:
            raise TaggingValidationError("优化会话已过期（约 30 分钟），请点「重新生成」重新联想")
        user_msg = {"role": "user", "content": SUGGEST_REFINE_PROMPT.format(instruction=instruction)}
        messages = [*sess["messages"], user_msg]
    else:
        existing_tags = {t for g in existing_groups for t in g["tags"]}
        pool = "\n".join(f"- {g['group']}：{'、'.join(g['tags'][:6])}" for g in existing_groups)
        messages = [
            {"role": "system", "content": SUGGEST_SYSTEM_PROMPT},
            {"role": "user", "content": f"关键词：{keyword}\n\n现有标签体系（避免重复）：\n{pool or '（空）'}"},
        ]

    payload = {
        "model": agent["model_id"],
        "temperature": 0.7,
        "response_format": {"type": "json_object"},
        "messages": messages,
    }
    body = await _chat_completions(agent, payload)
    content = ""
    for choice in body.get("choices") or []:
        content = ((choice.get("message") or {}).get("content") or "").strip()
        if content:
            break
    if not content:
        raise RuntimeError("AI 未返回内容")

    data = _extract_json_object(content)
    raw_groups = data.get("groups")
    if not isinstance(raw_groups, list) or not raw_groups:
        raise RuntimeError(f"AI 返回结构不符（缺少 groups 数组）：{content[:200]}")

    existing_tags = {t for g in existing_groups for t in g["tags"]}
    out: list[dict] = []
    for g in raw_groups:
        if not isinstance(g, dict):
            continue
        name = str(g.get("name") or "").strip()
        tags: list[str] = []
        for t in g.get("tags") or []:
            t = str(t).strip().lstrip("#").strip()
            if t and t not in tags and t not in existing_tags:
                tags.append(t)
        if name and tags:
            out.append({"name": name, "tags": tags[:8]})
    if not out:
        raise RuntimeError("AI 未给出可用的分组建议（可能与现有标签全部重复），请换个关键词或优化指令重试")

    # 保存/续期会话：完整对话（含本轮 user 与 assistant 原始 JSON）供后续「继续优化」
    messages.append({"role": "assistant", "content": content})
    if refine and session_id in _SUGGEST_SESSIONS:
        _SUGGEST_SESSIONS[session_id]["messages"] = messages
        _SUGGEST_SESSIONS[session_id]["expires_at"] = time.time() + SUGGEST_SESSION_TTL
    else:
        session_id = session_id or new_id("sgs")
        _SUGGEST_SESSIONS[session_id] = {
            "messages": messages,
            "expires_at": time.time() + SUGGEST_SESSION_TTL,
        }
    return out, session_id


async def test_agent(agent: dict) -> dict:
    """连通性测试：按打标方式发送最小请求验证 base_url / api_key。"""
    import time

    start = time.monotonic()
    try:
        if agent.get("provider") == "jev":
            answers = await _jev_decisions(
                agent, {"headline": "connectivity test"},
                {"ok": {"type": "noul", "instructions": "Is one plus one equal to two?"}},
            )
            reply = f"noul={(answers.get('ok') or {}).get('noul')}"
        else:
            payload = {"model": agent["model_id"], "messages": [{"role": "user", "content": "请直接回复：OK"}]}
            body = await _chat_completions(agent, payload)
            reply = ""
            for choice in body.get("choices") or []:
                reply = ((choice.get("message") or {}).get("content") or "").strip()
                if reply:
                    break
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}
    return {"ok": True, "latency_ms": round((time.monotonic() - start) * 1000), "reply": str(reply)[:50]}


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
