"""API + 数据层冒烟测试（不依赖浏览器内核）。

运行：.venv/Scripts/python.exe tests/smoke_test.py
覆盖：平台元信息、账号 CRUD、登录前置校验、抓取参数校验、任务记录、
收藏数据入库回读、删除账号、Web 页面渲染。
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

# 必须在导入 app 之前设置独立数据目录，避免污染真实数据
os.environ["FAVAPI_DATA_DIR"] = tempfile.mkdtemp(prefix="favapi_smoke_")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app.server import app as fastapp  # noqa: E402
from app.services import data_store  # noqa: E402
from app.utils import new_id, now_iso  # noqa: E402


def _fake_items():
    return [
        {
            "content_id": f"aweme_{i}",
            "title": f"测试视频 {i}",
            "description": f"描述 {i}",
            "author_id": "u1",
            "author_name": "作者",
            "cover_url": f"https://example.com/{i}.jpg",
            "duration": 1000 * i,
            "statistics": '{"digg_count": 10}',
            "raw_data": '{"aweme_id": "%s"}' % f"aweme_{i}",
            "collected_at": None,
        }
        for i in range(1, 4)
    ]


async def _checks(client: httpx.AsyncClient) -> int:
    failed = 0

    def check(name, cond, extra=""):
        nonlocal failed
        if cond:
            print(f"PASS {name}")
        else:
            failed += 1
            print(f"FAIL {name} {extra}")

    # 1. 平台元信息
    r = await client.get("/api/v1/platforms")
    platforms = {p["platform"]: p for p in r.json()["platforms"]}
    check("platforms.douyin_implemented", platforms["douyin"]["implemented"] is True)
    check("platforms.bilibili_placeholder", platforms["bilibili"]["implemented"] is False)

    # 2. 创建账号
    r = await client.post("/api/v1/accounts", json={"platform": "douyin", "name": "主号"})
    check("accounts.create", r.status_code == 201, r.text)
    acc = r.json()
    check("accounts.create_id_prefix", acc["account_id"].startswith("acc_"))

    r = await client.post("/api/v1/accounts", json={"platform": "bilibili", "name": "B站"})
    check("accounts.create_bilibili_blocked", r.status_code == 400 and "即将支持" in r.json()["detail"], r.text)

    r = await client.post("/api/v1/accounts", json={"platform": "xxx", "name": "?"})
    check("accounts.create_unknown_platform", r.status_code == 400)

    # 3. 列表 / 详情 / 更新
    r = await client.get("/api/v1/accounts")
    check("accounts.list_contains", any(a["account_id"] == acc["account_id"] for a in r.json()["accounts"]))
    r = await client.get(f"/api/v1/accounts/{acc['account_id']}")
    check("accounts.detail", r.status_code == 200 and r.json()["platform"] == "douyin")
    r = await client.get("/api/v1/accounts/acc_notexist")
    check("accounts.detail_404", r.status_code == 404)

    r = await client.patch(f"/api/v1/accounts/{acc['account_id']}", json={"status": "disabled"})
    check("accounts.disable", r.json()["status"] == "disabled")

    # 4. 抓取请求校验（不触浏览器）
    base = {"platform": "douyin", "account_id": acc["account_id"], "action": "list_favorites"}
    r = await client.post("/api/v1/fetch", json=base)
    check("fetch.disabled_account_400", r.status_code == 400 and "禁用" in r.json()["detail"], r.text)
    await client.patch(f"/api/v1/accounts/{acc['account_id']}", json={"status": "active"})

    r = await client.post("/api/v1/fetch", json={**base, "platform": "bilibili"})
    check("fetch.platform_mismatch_400", r.status_code == 400 and "不一致" in r.json()["detail"])
    r = await client.post("/api/v1/fetch", json={**base, "account_id": "acc_none"})
    check("fetch.unknown_account_400", r.status_code == 400)
    r = await client.post("/api/v1/fetch", json={**base, "action": "list_collects"})
    check("fetch.unsupported_action_400", r.status_code == 400 and "不支持" in r.json()["detail"])

    # 5. Bilibili 账号的抓取（直接写库模拟未来状态）→ 友好提示
    bili_acc_id = new_id("acc")
    await data_store.db.execute(
        """INSERT INTO accounts (account_id, platform, name, status, created_at)
           VALUES (?, 'bilibili', 'B站占位', 'active', ?)""",
        (bili_acc_id, now_iso()),
    )
    r = await client.post("/api/v1/fetch", json={
        "platform": "bilibili", "account_id": bili_acc_id, "action": "list_favorites",
    })
    check("fetch.bilibili_not_implemented_400", r.status_code == 400 and "暂未实现" in r.json()["detail"], r.text)

    # 6. 任务记录生命周期
    task_id = new_id("task")
    await data_store.create_task(task_id, acc["account_id"], "douyin", "list_favorites", {"count": 20})
    await data_store.update_task(task_id, status="success", result_count=3, started_at=now_iso(), finished_at=now_iso())
    r = await client.get(f"/api/v1/tasks/{task_id}")
    check("tasks.detail", r.status_code == 200 and r.json()["status"] == "success")
    r = await client.get("/api/v1/tasks")
    check("tasks.list_contains", any(t["task_id"] == task_id for t in r.json()["tasks"]))

    # 7. 收藏数据入库 → API 回读
    account_row = (await client.get(f"/api/v1/accounts/{acc['account_id']}")).json()
    summary = await data_store.save_fetch_result(account_row, _fake_items())
    check("favorites.saved_count", summary["result_count"] == 3 and summary["new_favorites"] == 3)
    summary2 = await data_store.save_fetch_result(account_row, _fake_items())
    check("favorites.dedup_on_refetch", summary2["new_favorites"] == 0)

    r = await client.get(f"/api/v1/favorites?account_id={acc['account_id']}")
    body = r.json()
    check("favorites.api_total", body["total"] == 3, r.text)
    check("favorites.api_item_fields", body["items"][0]["url"].startswith("https://www.douyin.com/video/"))
    r = await client.get(f"/api/v1/favorites?account_id={acc['account_id']}&limit=2&offset=2")
    check("favorites.pagination", len(r.json()["items"]) == 1 and r.json()["total"] == 3)

    # 8. 删除账号 → 收藏关系清空、内容保留
    r = await client.delete(f"/api/v1/accounts/{acc['account_id']}")
    check("accounts.delete", r.status_code == 200)
    r = await client.get(f"/api/v1/favorites?account_id={acc['account_id']}")
    check("favorites.cleared_after_delete", r.json()["total"] == 0)
    row = await data_store.db.query_one(
        "SELECT COUNT(*) AS n FROM contents WHERE platform='douyin'")
    check("contents.kept_after_delete", row["n"] == 3)

    # 9. Web 页面
    for path in ("/", "/tasks", "/favorites"):
        r = await client.get(path)
        check(f"web.page {path}", r.status_code == 200 and "FavAPI" in r.text)

    # 10. OpenAPI
    r = await client.get("/openapi.json")
    check("openapi", r.status_code == 200)

    return failed


async def main():
    async with fastapp.router.lifespan_context(fastapp):
        transport = httpx.ASGITransport(app=fastapp)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            failed = await _checks(client)
    print("\n冒烟测试完成" + ("" if failed == 0 else f"，{failed} 项失败"))
    return failed


if __name__ == "__main__":
    sys.exit(1 if asyncio.run(main()) else 0)
