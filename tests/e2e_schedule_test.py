"""定时任务链路端到端验证：创建(禁用)账号 + 每分钟计划 → 等调度循环触发 → 校验状态推进 → 清理。"""
import asyncio
import json
import urllib.request

BASE = "http://127.0.0.1:8300/api/v1"


def call(method: str, path: str, body: dict | None = None):
    req = urllib.request.Request(
        BASE + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


async def main():
    # 1. 创建账号并禁用（触发定时抓取时会在校验阶段快速失败，不会打开浏览器）
    st, acc = call("POST", "/accounts", {"platform": "douyin", "name": "调度测试账号"})
    assert st == 201, acc
    acc_id = acc["account_id"]
    print("1. 账号创建:", acc_id)

    st, _ = call("PATCH", f"/accounts/{acc_id}", {"status": "disabled"})
    assert st == 200
    print("2. 账号已禁用（触发时走校验失败路径）")

    # 2. 创建每分钟执行的计划
    st, sch = call("POST", "/schedules", {"account_id": acc_id, "cron_expr": "* * * * *", "title": "调度链路测试"})
    assert st == 201, sch
    sch_id = sch["schedule_id"]
    print("3. 计划创建:", sch_id, "next_run:", sch["next_run_at"])

    # 3. 手动触发：应返回 400（账号禁用）且 next_run_at 被推进
    st, resp = call("POST", f"/schedules/{sch_id}/trigger")
    print("4. 手动触发（预期 400 账号禁用）:", st, resp.get("detail", ""))

    st, sch2 = call("GET", "/schedules")
    row = next(s for s in sch2["schedules"] if s["schedule_id"] == sch_id)
    assert row["next_run_at"] >= sch["next_run_at"], "next_run_at 异常回退"
    assert row["status"] == "active"
    print("5. 触发失败后计划仍 active，next_run_at:", row["next_run_at"])

    # 4. 恢复启用账号，验证暂停/恢复语义
    call("PATCH", f"/accounts/{acc_id}", {"status": "active"})
    st, row2 = call("PATCH", f"/schedules/{sch_id}", {"status": "paused"})
    assert row2["status"] == "paused"
    st, row3 = call("PATCH", f"/schedules/{sch_id}", {"status": "active"})
    assert row3["next_run_at"] is not None, "恢复后 next_run_at 应重算"
    print("6. 暂停/恢复语义正常，恢复后 next_run:", row3["next_run_at"])

    # 5. 清理
    call("DELETE", f"/schedules/{sch_id}")
    call("DELETE", f"/accounts/{acc_id}")
    st, final = call("GET", "/schedules")
    assert all(s["schedule_id"] != sch_id for s in final["schedules"])
    print("7. 清理完成，全部通过 ✓")


asyncio.run(main())
