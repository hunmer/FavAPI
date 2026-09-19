# 假设验证：headless + context user_agent override（覆盖 Worker UA）→ 签名请求是否恢复
import asyncio
import json
import sys
from urllib.parse import urlencode

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

from playwright.async_api import async_playwright

from app.platforms.tiktok import api_client, constants

PROFILE = r"G:\programming\python\FavAPI\data\profiles\tiktok_acc_49b93540"
AUTHOR = "MS4wLjABAAAAMD9QNozl_qUOumzpMwQvOQ6GqohcgpDEHHW0pffggx9ik6iXixDLLBJp-m12jL0v"
NORMAL_UA = constants.USER_AGENT

WORKER_UA_JS = """async () => {
  const blob = new Blob([\"onmessage = e => postMessage(navigator.userAgent)\"],
                        {type: 'application/javascript'});
  const w = new Worker(URL.createObjectURL(blob));
  return await new Promise(res => { w.onmessage = ev => { w.terminate(); res(ev.data); }; });
}"""


async def run_case(ua_override: bool, label: str):
    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            user_data_dir=PROFILE, headless=True, channel="chromium",
            viewport={"width": 1280, "height": 860},
            args=["--disable-blink-features=AutomationControlled"],
            proxy={"server": "http://127.0.0.1:7890"},
            **({"user_agent": NORMAL_UA} if ua_override else {}),
        )
        try:
            page = await ctx.new_page()
            await page.goto(constants.FETCH_PAGE_URL, wait_until="commit", timeout=60000)
            await page.wait_for_function(api_client._FETCH_HOOK_READY_JS, timeout=20000)
            main_ua = await page.evaluate("() => navigator.userAgent")
            worker_ua = await page.evaluate(WORKER_UA_JS)
            text = await page.evaluate(api_client._PAGE_FETCH_JS, {
                "path": "/node-webapp/api/common-app-context", "query": ""})
            user = (json.loads(text) if text.strip() else {}).get("user") or {}
            params = api_client._post_list_params(AUTHOR, str(user.get("uid") or ""), 0, 16)
            results = []
            for attempt in range(1, 3):
                text = await page.evaluate(api_client._PAGE_FETCH_JS, {
                    "path": constants.POST_LIST_PATH, "query": urlencode(params)})
                ok = bool(text and text.strip())
                results.append(ok)
                if ok:
                    break
                await asyncio.sleep(2)
            print(f"--- {label}")
            print(f"    main UA: ...{main_ua[-40:]}")
            print(f"    worker UA: ...{worker_ua[-40:]}")
            print(f"    fetch 结果: {results}")
            await page.close()
        finally:
            await ctx.close()


asyncio.run(run_case(False, "headless 默认 UA"))
asyncio.run(run_case(True, "headless + UA override（正常 Chrome UA）"))
