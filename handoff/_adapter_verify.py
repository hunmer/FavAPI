# adapter 直测：模拟 follows 完整链路（cookie → 关注列表 → 作品翻页 → 播放 + 媒体直链）
import asyncio
import json
import sys
import time

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

from app.platforms import registry
from app.platforms.base import AccountContext
from app.services import follow_store
from app.database import db
from curl_cffi import requests as curl_requests

ACC_ID = "acc_49b93540"
PROFILE = r"G:\programming\python\FavAPI\data\profiles\tiktok_acc_49b93540"


async def main():
    await db.connect()
    adapter = registry.get_adapter("tiktok")
    assert adapter.follows_api_implemented
    ctx = AccountContext(account_id=ACC_ID, platform="tiktok",
                         name="TikTok账号", profile_path=PROFILE)

    # 1. cookie + self_uid
    t0 = time.time()
    cookie = await adapter.follows_profile_cookie(ctx)
    self_uid = adapter.follows_self_uid(cookie)
    print(f"[1] cookie OK ({time.time()-t0:.1f}s), self_uid={self_uid[:24]}...")
    assert self_uid

    # 2. 校验非法 uid
    try:
        adapter.follows_validate_uid("!!!bad")
        print("[2] FAIL: 非法 uid 未拒绝")
    except ValueError:
        print("[2] 非法 uid 正确抛 ValueError")

    # 3. 关注列表
    t0 = time.time()
    followings, has_more = await adapter.follows_fetch_following(cookie, self_uid)
    print(f"[3] 关注列表 {len(followings)} 条, has_more={has_more} ({time.time()-t0:.1f}s)")
    author = next(f for f in followings if f["nickname"])  # 选一个博主测后续链路
    print("    博主:", author["nickname"], author["sec_uid"][:24], "...")

    # 4. 作品页两页（验证 shared_page 复用：第二次应显著变快）
    t0 = time.time()
    p1 = await adapter.follows_fetch_posts_page(cookie, author["sec_uid"], 0, 18)
    d1 = time.time() - t0
    t0 = time.time()
    p2 = await adapter.follows_fetch_posts_page(cookie, author["sec_uid"], p1["cursor"], 18)
    d2 = time.time() - t0
    ids1 = {it["content_id"] for it in p1["items"]}
    ids2 = {it["content_id"] for it in p2["items"]}
    print(f"[4] 作品页1: {len(p1['items'])} 条 cursor={p1['cursor']} ({d1:.1f}s)；"
          f"页2: {len(p2['items'])} 条 ({d2:.1f}s)，重叠 {len(ids1 & ids2)}")
    assert d2 < d1, "shared_page 复用未生效（第二次应更快）"

    # 5. 播放信息 + 媒体直链（经 register_media_cookie 后的 media 请求头组合）
    item_id = p1["items"][0]["content_id"]
    info = await adapter.follows_play_info(cookie, item_id)
    print(f"[5] play_info: id={info['aweme_id']}, video_urls={len(info['video_urls'])}, "
          f"images={len(info['images'])}, duration={info['duration']}s, "
          f"stats.digg={info['statistics']['digg_count']}")
    url = (info["video_urls"] or [next((i["url"] for i in info["images"]), None)])[0]
    assert url
    headers = {"user-agent": follow_store.MEDIA_UA}
    ref = follow_store.media_referer(url)
    if ref:
        headers["referer"] = ref
    ck = follow_store.media_cookies(url)
    assert ck, "媒体 cookie 未登记"
    headers["cookie"] = ck
    headers["range"] = "bytes=0-65535"
    r = curl_requests.get(url, headers=headers, impersonate="chrome",
                          timeout=30, proxy=follow_store.media_proxy(url), stream=True)
    first = next(r.iter_content(1024), None)
    print(f"[5] 媒体直链: HTTP {r.status_code}, content-range={r.headers.get('content-range')}, "
          f"首块={len(first or b'')}")
    r.close()
    assert r.status_code in (200, 206)

    # 6. 同步（真实入库前调 adapter；不落库）
    author_row = {"sec_uid": author["sec_uid"], "uid": author.get("uid") or "",
                  "nickname": author.get("nickname") or "",
                  "avatar_url": author.get("avatar_url") or ""}
    t0 = time.time()
    items = await adapter.sync_author_posts(ctx, author_row, cookie, 3)
    print(f"[6] sync_author_posts: {len(items)} 条 ({time.time()-t0:.1f}s)，"
          f"author_id 均为 sec_uid: {all(i['author_id'] == author['sec_uid'] for i in items)}")
    print("    首条:", json.dumps({k: items[0][k] for k in
          ("content_id", "title", "author_id", "collected_at")}, ensure_ascii=False)[:120])

    print("\n全部通过 ✅")


asyncio.run(main())
