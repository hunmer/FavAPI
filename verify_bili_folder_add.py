"""临时端到端测试：folder/add 建测试夹 → 打印 media_id（编辑/删除走 HTTP 路由测试）。"""
import sys
from urllib.parse import urlencode

from curl_cffi import requests

COOKIE = (
    "buvid3=C48FD4B6-A7FE-9F62-DDBC-8161CD2D1BAD03749infoc; "
    "buvid_fp=beb1ae54a9a6ef8ef8311e11292d3714; "
    "DedeUserID=388116545; "
    "SESSDATA=fa0dce03%2C1804985906%2C7f7a3%2A91CjDZIzEUh9InEu1gBSU1e0Xgha8nl9ckc55p5OZu0zDwt_yzBhpaWpDEG8-RvzuyZYoSVnNnc09PRkEybjNTckJMemJ3cExHX25WMlZTeHhpTndLZjMzVXVZN2hGWmtITVlCYVJ2YjgzeHBYY2lncXAzRENjcXZZUmt6MWdqUmdHRnNURmk4OEF3IIEC; "
    "bili_jct=3e7a5a9eb38aeb36aa9c1461f8243996"
)
HEADERS = {
    "accept": "*/*",
    "origin": "https://space.bilibili.com",
    "referer": "https://space.bilibili.com/388116545/favlist",
    "cookie": COOKIE,
}


def main():
    body = urlencode({
        "title": "FavAPI临时测试夹",
        "privacy": 0,
        "csrf": "3e7a5a9eb38aeb36aa9c1461f8243996",
    })
    resp = requests.post(
        "https://api.bilibili.com/x/v3/fav/folder/add",
        data=body,
        headers={**HEADERS, "content-type": "application/x-www-form-urlencoded"},
        impersonate="chrome", timeout=20,
    )
    payload = resp.json()
    print(payload.get("code"), payload.get("message"))
    print(payload.get("data", {}).get("id"))
    if payload.get("code") != 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
