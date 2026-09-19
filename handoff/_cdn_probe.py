# TikTok CDN 直链可达性 2：完整 URL（tk 参数）+ 各 cookie 组合
import sys

from curl_cffi import requests

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

from app.platforms.tiktok import api_client, constants

PROXY = "http://127.0.0.1:7890"
UA = constants.USER_AGENT
ITEM_ID = "7685525367708224776"

result = api_client.fetch_post_detail(ITEM_ID)
video_link = next((l for l in result["links"] if l.get("kind") == "video"), None)
image_link = next((l for l in result["links"] if l.get("kind") == "image"), None)
session_cookie = result.get("cookie_header") or ""
print("匿名会话 cookie:", session_cookie[:100])
print("有无 tt_chain_token:", "tt_chain_token" in session_cookie)

for label, link in (("视频", video_link), ("图片", image_link)):
    if not link:
        continue
    url = link["url"]
    print(f"\n=== {label} 直链: {url}")
    cases = [
        ("仅 UA", {"user-agent": UA}),
        ("UA + 匿名会话 cookie", {"user-agent": UA, "cookie": session_cookie}),
    ]
    for label2, headers in cases:
        try:
            r = requests.get(url, headers=headers, impersonate="chrome",
                             timeout=20, proxy=PROXY, stream=True)
            first = next(r.iter_content(1024), None)
            code, clen = r.status_code, r.headers.get("content-length")
            r.close()
            print(f"  [{label2}] {code} len={clen} 首块={len(first or b'')}")
        except Exception as exc:
            print(f"  [{label2}] 异常: {str(exc)[:100]}")
