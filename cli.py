"""FavAPI 命令行：python cli.py <command> [args]

不依赖服务运行，直接调用各平台 API（共用同一 SQLite 数据与浏览器登录态）：

    python cli.py platforms                     # 列出平台及其可用的抓取目标 / API 操作
    python cli.py accounts                      # 列出账号
    python cli.py fetch <account_id> [action] -p count=20
    python cli.py op <account_id> <op_id> -p key=value

fetch 走 /api/v1/fetch 同一任务管线（校验 → 抓取 → 入库 → 任务记录）；
op 执行平台 adapter 暴露的 API 操作（写操作/管理类，同步返回结果）。
参数用 -p k=v 重复传入，值自动转 int / bool，其余按字符串处理。
"""
import argparse
import asyncio
import json
import sys

# Windows 控制台默认 GBK，中文输出乱码
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")


def _print_json(data):
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _parse_kv(items: list[str]) -> dict:
    """-p k=v 参数列表 → dict；值做 int / bool 自动转换，其余保持字符串。"""
    params = {}
    for item in items:
        if "=" not in item:
            raise SystemExit(f"参数格式应为 k=v：{item}")
        key, _, value = item.partition("=")
        if value.lower() in ("true", "false"):
            params[key] = value.lower() == "true"
        else:
            try:
                params[key] = int(value)
            except ValueError:
                params[key] = value
    return params


def _fail(message: str) -> SystemExit:
    print(f"[错误] {message}", file=sys.stderr)
    return SystemExit(1)


async def cmd_platforms(args):
    from app.platforms import registry

    infos = registry.platform_infos()
    if args.json:
        _print_json(infos)
        return
    for info in infos:
        mark = "" if info["implemented"] else "（未实现）"
        print(f"{info['platform']:<14} {info['display_name']}{mark}")
        for t in info["fetch_targets"]:
            keys = ",".join(p["key"] for p in t["params"])
            print(f"  fetch {t['action']:<26} {t['name']}  ({keys})")
        for op in info["api_operations"]:
            keys = ",".join(p["key"] for p in op["params"])
            danger = " [危险]" if op["danger"] else ""
            print(f"  op    {op['op_id']:<26} {op['name']}{danger}  ({keys})")


async def cmd_accounts(args):
    from app.services import account_manager

    accounts = await account_manager.list_accounts()
    if args.json:
        _print_json(accounts)
        return
    if not accounts:
        print("暂无账号（可先启动 python main.py 在 Web 界面扫码登录）")
        return
    for a in accounts:
        name = a.get("name") or "-"
        print(f"{a['account_id']:<18} {a['platform']:<12} {a.get('status', ''):<10} {name}")


async def cmd_fetch(args):
    from app.platforms import registry
    from app.services import account_manager, data_store
    from app.services.task_executor import (
        FetchValidationError,
        start_fetch,
        stream_fetch_events,
        validate_fetch,
    )
    from app.utils import new_id

    account = await account_manager.get_account(args.account_id)
    if account is None:
        raise _fail(f"账号不存在：{args.account_id}")
    adapter = registry.get_adapter(account["platform"])
    action = args.action or adapter.effective_fetch_targets()[0].action
    params = _parse_kv(args.params)

    if action == "ai_tag":  # AI 打标走独立任务管线（无逐批进度）
        try:
            result = await start_fetch(account["platform"], args.account_id, action, params)
        except ValueError as exc:  # FetchValidationError 等校验问题
            raise _fail(str(exc))
        _print_json(result)
        if result.get("status") != "success":
            raise _fail(result.get("error_message") or "抓取失败")
        return

    try:
        account, adapter = await validate_fetch(account["platform"], args.account_id, action, params)
    except FetchValidationError as exc:
        raise _fail(str(exc))

    task_id = new_id("task")
    await data_store.create_task(task_id, args.account_id, account["platform"], action, params)

    # 流式管线逐批推送：进度行打 stderr（不污染 stdout 的 JSON 结果），结束打汇总 JSON
    final = None
    async for msg in stream_fetch_events(task_id, account, adapter, action, params):
        kind = msg.get("type")
        if kind == "items":
            folder = msg.get("folder")
            label = f" · {folder}" if folder else ""
            print(
                f"[进度] 已抓取 {msg.get('total_fetched') or 0} 条（本批 {msg.get('new_count')}）{label}",
                file=sys.stderr, flush=True,
            )
        elif kind == "done":
            final = {"task_id": task_id, "status": "success",
                     **{k: v for k, v in msg.items() if k != "type"}}
        elif kind == "error":
            final = {"task_id": task_id, "status": "failed", "error_message": msg.get("error_message")}

    _print_json(final)
    if final.get("status") != "success":
        raise _fail(final.get("error_message") or "抓取失败")


async def cmd_op(args):
    from app.platforms.base import LoginExpiredError
    from app.services import account_manager

    account = await account_manager.get_account(args.account_id)
    if account is None:
        raise _fail(f"账号不存在：{args.account_id}")
    from app.platforms import registry

    adapter = registry.get_adapter(account["platform"])
    if adapter is None or adapter.get_api_operation(args.op_id) is None:
        raise _fail(f"{account['platform']} 不支持操作：{args.op_id}（cli.py platforms 可查看全部操作）")
    if account["status"] == "disabled":
        raise _fail(f"账号 {args.account_id} 已禁用，请先启用")
    try:
        result = await adapter.execute_api_operation(
            args.op_id, account_manager.to_context(account), _parse_kv(args.params)
        )
    except LoginExpiredError as exc:
        await account_manager.update_account(args.account_id, status="expired")
        raise _fail(f"登录态已失效：{exc}")
    except ValueError as exc:
        raise _fail(str(exc))
    _print_json({"account_id": args.account_id, "op_id": args.op_id, "result": result})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cli.py", description="FavAPI 命令行：直接调用各平台 API")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("platforms", help="列出平台及可用的抓取目标 / API 操作")
    p.add_argument("--json", action="store_true", help="输出完整 JSON（含参数定义）")
    p.set_defaults(func=cmd_platforms)

    p = sub.add_parser("accounts", help="列出账号")
    p.add_argument("--json", action="store_true", help="输出完整 JSON")
    p.set_defaults(func=cmd_accounts)

    p = sub.add_parser("fetch", help="抓取入库（走任务管线，action 缺省为平台首个抓取目标）")
    p.add_argument("account_id")
    p.add_argument("action", nargs="?", help="抓取目标 action（如 list_favorites）")
    p.add_argument("-p", "--param", action="append", default=[], dest="params", metavar="k=v",
                   help="抓取参数，可重复（如 -p count=20 -p method=api）")
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("op", help="执行平台 API 操作（写操作/管理类）")
    p.add_argument("account_id")
    p.add_argument("op_id", help="操作 ID（cli.py platforms 可查看）")
    p.add_argument("-p", "--param", action="append", default=[], dest="params", metavar="k=v",
                   help="操作参数，可重复（如 -p title=新建夹）")
    p.set_defaults(func=cmd_op)
    return parser


async def main():
    args = build_parser().parse_args()
    from app.database import db

    await db.connect()  # 只初始化数据层，不启动调度器 / 下载等工作器
    try:
        await args.func(args)
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
