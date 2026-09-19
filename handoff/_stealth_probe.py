# stealth 实验：headless 指纹采集 + init_script 补丁后 evaluate fetch 是否通过
import asyncio
import json
import sys
import time
from urllib.parse import urlencode

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

from playwright.async_api import async_playwright

from app.platforms.tiktok import api_client, constants

PROFILE = r"G:\programming\python\FavAPI\data\profiles\tiktok_acc_49b93540"
AUTHOR = "MS4wLjABAAAAMD9QNozl_qUOumzpMwQvOQ6GqohcgpDEHHW0pffggx9ik6iXixDLLBJp-m12jL0v"

FINGERPRINT_JS = """() => {
  const fp = {};
  try { fp.webdriver = navigator.webdriver; } catch (e) {}
  try { fp.plugins = navigator.plugins.length; } catch (e) {}
  try { fp.languages = navigator.languages; } catch (e) {}
  try { fp.chrome = typeof window.chrome; } catch (e) {}
  try { fp.visibility = document.visibilityState; } catch (e) {}
  try { fp.hasFocus = document.hasFocus(); } catch (e) {}
  try {
    const gl = document.createElement('canvas').getContext('webgl');
    const dbg = gl.getExtension('WEBGL_debug_renderer_info');
    fp.glVendor = gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL);
    fp.glRenderer = gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL);
  } catch (e) { fp.gl = 'err'; }
  try { fp.permissions = Notification.permission; } catch (e) {}
  try { fp.hardwareConcurrency = navigator.hardwareConcurrency; } catch (e) {}
  try { fp.deviceMemory = navigator.deviceMemory; } catch (e) {}
  try { fp.ua = navigator.userAgent; } catch (e) {}
  try { fp.touchPoints = navigator.maxTouchPoints; } catch (e) {}
  return fp;
}"""

# 常见 headless 破绽补丁（stealth 手法）
STEALTH_INIT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(document, 'visibilityState', {get: () => 'visible'});
Object.defineProperty(document, 'hidden', {get: () => false});
window.chrome = window.chrome || {runtime: {}, app: {isInstalled: false}};
Object.defineProperty(navigator, 'plugins', {get: () => [
  {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer'},
  {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai'},
  {name: 'Native Client', filename: 'internal-nacl-plugin'},
]});
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
"""


async def run_case(stealth: bool, label: str):
    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            user_data_dir=PROFILE, headless=True, channel="chromium",
            viewport={"width": 1280, "height": 860},
            args=["--disable-blink-features=AutomationControlled"],
            proxy={"server": "http://127.0.0.1:7890"},
        )
        try:
            page = await ctx.new_page()
            if stealth:
                await page.add_init_script(STEALTH_INIT)
            await page.goto(constants.FETCH_PAGE_URL, wait_until="commit", timeout=60000)
            await page.wait_for_function(api_client._FETCH_HOOK_READY_JS, timeout=20000)
            fp = await page.evaluate(FINGERPRINT_JS)
            print(f"--- {label} 指纹:", json.dumps(fp, ensure_ascii=False)[:500])
            text = await page.evaluate(api_client._PAGE_FETCH_JS, {
                "path": "/node-webapp/api/common-app-context", "query": ""})
            user = (json.loads(text) if text.strip() else {}).get("user") or {}
            params = api_client._post_list_params(AUTHOR, str(user.get("uid") or ""), 0, 16)
            ok = False
            for attempt in range(1, 4):
                text = await page.evaluate(api_client._PAGE_FETCH_JS, {
                    "path": constants.POST_LIST_PATH, "query": urlencode(params)})
                ok = bool(text and text.strip())
                print(f"  {label} fetch 尝试 {attempt}: resp len={len(text or '')}")
                if ok:
                    break
                await asyncio.sleep(2)
            await page.close()
        finally:
            await ctx.close()


asyncio.run(run_case(False, "headless 无补丁"))
asyncio.run(run_case(True, "headless+stealth补丁"))
