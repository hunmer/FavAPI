"""临时验证：bilibili 按窗口批量取消收藏（先小批量 max_delete=2 真删）。"""
import asyncio
import math

from app.platforms.bilibili import api_client
from app.utils import parse_date_window

# 来自用户抓包 curl 的关键 cookie（cmd 转义已还原为 %XX）
COOKIE = (
    "buvid3=C48FD4B6-A7FE-9F62-DDBC-8161CD2D1BAD03749infoc; "
    "buvid_fp=beb1ae54a9a6ef8ef8311e11292d3714; "
    "DedeUserID=388116545; "
    "SESSDATA=fa0dce03%2C1804985906%2C7f7a3%2A91CjDZIzEUh9InEu1gBSU1e0Xgha8nl9ckc55p5OZu0zDwt_yzBhpaWpDEG8-RvzuyZYoSVnNnc09PRkEybjNTckJMemJ3cExHX25WMlZTeHhpTndLZjMzVXVZN2hGWmtITVlCYVJ2YjgzeHBYY2lncXAzRENjcXZZUmt6MWdqUmdHRnNURmk4OEF3IIEC; "
    "bili_jct=3e7a5a9eb38aeb36aa9c1461f8243996"
)
MEDIA_ID = "290999545"
MAX_DELETE = 2  # 先删 2 条验证


async def main():
    # 1) 只读：看最旧一页的收藏时间（确认 2026 之前的条目存在）
    head = api_client.fetch_resource_list_page(COOKIE, MEDIA_ID, pn=1, ps=1)
    total = head["total"]
    last_pn = max(1, math.ceil(total / api_client.constants.PAGE_SIZE))
    tail = api_client.fetch_resource_list_page(COOKIE, MEDIA_ID, pn=last_pn)
    print(f"删除前总数: {total}（共 {last_pn} 页）")
    print(f"最新一条收藏于: {head['items'][0]['collected_at']}")
    print(f"最旧一页（pn={last_pn}）收藏时间范围: "
          f"{tail['items'][-1]['collected_at']} ~ {tail['items'][0]['collected_at']}")

    # 2) 2026 年之前 = date_to=2025-12-31（闭区间含当天）
    dt_from, dt_to = parse_date_window({"date_to": "2025-12-31"})

    async def on_progress(info: dict):
        if "batch_no" in info:  # 删除批次进度
            print("  [删除]", info)
        elif info.get("page", 0) % 10 == 0 or info.get("matched_this_page"):
            print("  [扫描]", info)

    result = await api_client.cancel_fav_by_window(
        COOKIE, dt_from, dt_to, media_id=MEDIA_ID,
        on_progress=on_progress, max_delete=MAX_DELETE,
    )
    print("cancel_fav_by_window 结果:", result)

    # 3) 复查计数
    after = api_client.fetch_resource_list_page(COOKIE, MEDIA_ID, pn=1, ps=1)
    print(f"删除后总数: {after['total']}（预期 {total - MAX_DELETE}）")


if __name__ == "__main__":
    asyncio.run(main())
