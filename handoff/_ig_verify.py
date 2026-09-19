# Instagram follows 接入验证（cookie 从环境变量 IG_COOKIE 传入，不落盘）
import asyncio
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.platforms import registry  # noqa: E402

COOKIE = os.environ.get("IG_COOKIE", "")


async def main():
    adapter = registry.get_adapter("instagram")
    assert adapter is not None, "instagram 未注册"

    # 1. 注册与元数据
    info = registry.get_platform_info("instagram")
    print("[1] info:", {k: info[k] for k in ("platform", "display_name",
          "api_fetch_implemented", "follows_api_implemented")},
          "icon:", info.get("icon_url"))

    # 2. self uid / 主键校验
    self_uid = adapter.follows_self_uid(COOKIE)
    print("[2] self_uid:", self_uid)
    try:
        adapter.follows_validate_uid("!!bad!!")
        print("    validate bad: FAIL（未抛错）")
    except ValueError:
        print("    validate bad -> ValueError ok")
    adapter.follows_validate_uid("luluniverse.official")
    print("    validate username ok")

    # 3. 关注列表
    followings, has_more = await adapter.follows_fetch_following(
        COOKIE, self_uid, count=15)
    print(f"[3] following: {len(followings)} 条 has_more={has_more}")
    if followings:
        print("    first:", json.dumps(followings[0], ensure_ascii=False)[:300])

    # 4. 博主作品两页（验证 cursor 归一语义）
    page1 = await adapter.follows_fetch_posts_page(
        COOKIE, "luluniverse.official", 0, 6)
    print(f"[4] posts p1: {len(page1['items'])} 条 cursor={page1['cursor']} "
          f"has_more={page1['has_more']}")
    it = page1["items"][0]
    print("    first item:", json.dumps(
        {k: it.get(k) for k in ("content_id", "title", "author_id", "author_name",
                                "cover_url", "collected_at")}, ensure_ascii=False)[:400])
    if page1["cursor"]:
        page2 = await adapter.follows_fetch_posts_page(
            COOKIE, "luluniverse.official", page1["cursor"], 6)
        ids1 = {i["content_id"] for i in page1["items"]}
        ids2 = {i["content_id"] for i in page2["items"]}
        print(f"    posts p2: {len(page2['items'])} 条 cursor={page2['cursor']} "
              f"与 p1 重叠={bool(ids1 & ids2)}")

    # 5. 播放信息
    play = await adapter.follows_play_info(COOKIE, it["content_id"])
    print("[5] play:", json.dumps(
        {k: play.get(k) for k in ("aweme_id", "desc", "duration", "create_time",
                                  "statistics", "author")}, ensure_ascii=False)[:400])
    print("    video_urls:", len(play.get("video_urls") or []),
          "| images:", len(play.get("images") or []))

    # 6. 收藏列表一页（fetch 体系）
    from app.platforms.instagram import api_client
    saved = await asyncio.to_thread(api_client.fetch_saved_page, COOKIE)
    print(f"[6] saved page: {len(saved['items'])} 条 has_more={saved['has_more']} "
          f"cursor 非空={bool(saved['cursor'])}")
    if saved["items"]:
        s = saved["items"][0]
        print("    first:", json.dumps(
            {k: s.get(k) for k in ("content_id", "author_name", "cover_url",
                                   "collected_at")}, ensure_ascii=False)[:300])


asyncio.run(main())
