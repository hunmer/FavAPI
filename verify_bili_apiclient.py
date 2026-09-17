"""临时冒烟测试：只读验证 bilibili api_client（不执行删除）。"""
import asyncio
import json

from app.platforms.bilibili import api_client

# 来自用户抓包 curl 的关键 cookie（cmd 转义已还原为 %XX）
COOKIE = (
    "buvid3=C48FD4B6-A7FE-9F62-DDBC-8161CD2D1BAD03749infoc; "
    "buvid_fp=beb1ae54a9a6ef8ef8311e11292d3714; "
    "DedeUserID=388116545; "
    "SESSDATA=fa0dce03%2C1804985906%2C7f7a3%2A91CjDZIzEUh9InEu1gBSU1e0Xgha8nl9ckc55p5OZu0zDwt_yzBhpaWpDEG8-RvzuyZYoSVnNnc09PRkEybjNTckJMemJ3cExHX25WMlZTeHhpTndLZjMzVXVZN2hGWmtITVlCYVJ2YjgzeHBYY2lncXAzRENjcXZZUmt6MWdqUmdHRnNURmk4OEF3IIEC; "
    "bili_jct=3e7a5a9eb38aeb36aa9c1461f8243996"
)

MEDIA_ID = "290999545"


def main():
    csrf = api_client.csrf_from_cookie_header(COOKIE)
    assert csrf == "3e7a5a9eb38aeb36aa9c1461f8243996", csrf
    print("csrf 提取 OK:", csrf)
    print("referer:", api_client._referer(COOKIE, MEDIA_ID))

    batch = api_client.fetch_resource_list_page(COOKIE, MEDIA_ID, pn=1, ps=5)
    medias = json.loads(batch["items"][0]["raw_data"]) if batch["items"] else {}
    print("收藏夹:", batch["favorite"])
    print("本页条数:", len(batch["items"]), "has_more:", batch["has_more"], "total:", batch["total"])
    if medias:
        print("首条资源 id/type:", medias.get("id"), medias.get("type"), "bvid:", medias.get("bvid"))
    print("batch_del 所需 resources 形如:", f"{medias.get('id')}:{medias.get('type')}" if medias else "(空)")


if __name__ == "__main__":
    main()
