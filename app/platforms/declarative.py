"""声明式 JSON 平台适配器。用于无需编写 Python 的简单收藏接口。"""
import asyncio, json, logging, time, os, re
from app import config
from app.platforms.base import BasePlatformAdapter, FetchResult, AccountContext, LoginExpiredError
from app.services import browser

logger = logging.getLogger("favapi.declarative")

def _walk(obj, path):
    vals=[obj]
    for part in path.split('.') if path else []:
        nxt=[]; is_many=part.endswith('[]'); key=part[:-2] if is_many else part
        for v in vals:
            if isinstance(v,dict) and key in v:
                x=v[key]; nxt.extend(x if is_many and isinstance(x,list) else [x])
            elif is_many and isinstance(v,list): nxt.extend(v)
        vals=nxt
    return vals

class DeclarativeAdapter(BasePlatformAdapter):
    def __init__(self, spec: dict):
        self.spec=spec; self.platform=spec['platform']; self.display_name=spec.get('display_name',self.platform)
        self.home_url=spec.get('home_url',''); self.supported_actions=tuple(spec.get('supported_actions',['list_favorites']))
        self.implemented=bool(spec.get('implemented',True)); self._capture=spec.get('capture',{})

    def _proxy(self):
        value = self.spec.get('proxy')
        if isinstance(value, str):
            m = re.fullmatch(r"\$\{([^}]+)\}", value.strip())
            if m: return os.environ.get(m.group(1)) or None
        return value

    async def login(self, account, timeout=None):
        timeout=timeout or config.LOGIN_TIMEOUT; deadline=time.monotonic()+timeout
        async with browser.session(account.profile_path, headless=False, proxy=self._proxy()) as ctx:
            page=ctx.pages[0] if ctx.pages else await ctx.new_page(); await page.goto(self.home_url,wait_until='domcontentloaded')
            keys=tuple(self.spec.get('login_cookies',[]))
            while time.monotonic()<deadline:
                if browser.has_login_cookies(await ctx.cookies(),keys): return True
                await asyncio.sleep(3)
        return False

    async def check_login_status(self, account):
        async with browser.session(account.profile_path,headless=True, proxy=self._proxy()) as ctx:
            return browser.has_login_cookies(await ctx.cookies(),tuple(self.spec.get('login_cookies',[])))

    def validate_params(self, params):
        if not self.home_url: raise ValueError('平台未配置 home_url')

    @staticmethod
    def _value(obj, path, default=None):
        vals = _walk(obj, path)
        return vals[0] if vals else default

    async def fetch_favorites(self, account, params, on_batch=None):
        batches=[]; cap=self._capture; target=int(params.get('count') or 0)
        max_rounds = max(0, int(cap.get('max_rounds', 20)))
        scroll_step = int(cap.get('scroll_step', 2400))
        cursor = params.get('cursor'); has_more = False
        async with browser.session(account.profile_path,headless=config.HEADLESS, proxy=self._proxy()) as ctx:
            page=ctx.pages[0] if ctx.pages else await ctx.new_page()
            headers = dict(self.spec.get('headers') or {}); headers.update(cap.get('headers') or {})
            if headers:
                await ctx.set_extra_http_headers({str(k): str(v) for k, v in headers.items()})
            async def on_response(resp):
                nonlocal cursor, has_more
                if cap.get('url_contains') and cap['url_contains'] not in resp.url: return
                try: data=await resp.json()
                except Exception: return
                rows=_walk(data,cap.get('items_path',''))
                cursor = self._value(data, cap.get('cursor_path',''), cursor)
                has_more = bool(self._value(data, cap.get('has_more_path',''), has_more))
                items=[]
                for row in rows:
                    out={}
                    for dst,src in (cap.get('fields') or {}).items():
                        if isinstance(src, dict):
                            v = self._value(row, src.get('path',''), src.get('default'))
                            if src.get('type') == 'string' and v is not None: v = str(v)
                        else:
                            v=self._value(row,src)
                        out[dst]=v
                    if out.get('content_id'): out['content_id']=str(out['content_id']); out['raw_data']=json.dumps(row,ensure_ascii=False); items.append(out)
                if items:
                    batches.extend(items)
                    if on_batch: await on_batch({'page':len(batches),'items':items})
            page.on('response',on_response); await page.goto(cap.get('page_url') or self.home_url,wait_until='domcontentloaded'); await page.wait_for_timeout(int(cap.get('wait_ms',3000)))
            for _ in range(max_rounds):
                if (target and len({i['content_id'] for i in batches}) >= target) or (batches and not has_more):
                    break
                await page.mouse.wheel(0, scroll_step)
                await page.wait_for_timeout(int(cap.get('scroll_wait_ms', 1500)))
            if self.spec.get('login_cookies') and not browser.has_login_cookies(await ctx.cookies(),tuple(self.spec['login_cookies'])): raise LoginExpiredError(f'{self.display_name} 登录态缺失')
        uniq={i['content_id']:i for i in batches}; items=list(uniq.values()); items=items[:target] if target else items
        return FetchResult(items=items,total=len(items),cursor=cursor,has_more=has_more)
