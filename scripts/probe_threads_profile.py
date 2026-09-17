"""抓包：打开 threads 个人主页，捕获含 username/avatar 的 viewer 查询（doc_id/variables/响应）。"""
import asyncio
import io
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"G:\programming\python\FavAPI")

from app.services import browser

PROFILE = r"G:\programming\python\FavAPI\data\profiles\threads_acc_e2a8b586"
OUT = Path(__file__).parent / "threads_profile_capture.json"

captured: list[dict] = []


async def main():
    async with browser.session(PROFILE, headless=True) as ctx:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        async def on_response(resp):
            if "graphql" not in resp.url:
                return
            entry = {"url": resp.url, "status": resp.status}
            try:
                entry["post_data"] = resp.request.post_data
            except Exception:
                pass
            try:
                entry["response"] = await resp.json()
            except Exception:
                return
            captured.append(entry)

        page.on("response", on_response)
        await page.goto("https://www.threads.com/", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(6000)
        # 从侧边栏找个人主页链接 /@username
        href = await page.evaluate("""() => {
            const links = Array.from(document.querySelectorAll('a[href*="/@"]'));
            const profile = links.find(a => /\\/@[A-Za-z0-9._]+$/.test(a.getAttribute('href') || ''));
            return profile ? profile.getAttribute('href') : '';
        }""")
        print("profile link:", href)
        target = f"https://www.threads.com{href}" if href.startswith("/@") else "https://www.threads.com/"
        print("goto:", target)
        await page.goto(target, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(8000)

    OUT.write_text(json.dumps(captured, ensure_ascii=False, indent=1), encoding="utf-8")
    print("saved", OUT, "entries:", len(captured))
    # 找响应里同时含 username + profile_pic_url 的查询
    for i, e in enumerate(captured):
        text = json.dumps(e.get("response") or {})
        if '"username"' in text and "profile_pic_url" in text:
            fields = {k: v[0] for k, v in parse_qs(e.get("post_data") or "", keep_blank_values=True).items()}
            print(f"--- {i}: doc_id={fields.get('doc_id')} friendly={fields.get('fb_api_req_friendly_name')}")
            print("    variables:", str(fields.get("variables"))[:250])


asyncio.run(main())
