"""声明式 JSON 平台适配器。用于无需编写 Python 的简单收藏接口。"""
import asyncio, json, logging, time, os, re, subprocess, sys
from pathlib import Path
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
    def __init__(self, spec: dict, base_dir: Path | None = None):
        self.spec=spec; self.platform=spec['platform']; self.display_name=spec.get('display_name',self.platform)
        self.home_url=spec.get('home_url',''); self.homepage=spec.get('homepage') or self.home_url; self.icon=spec.get('icon',''); self.base_dir=base_dir
        self.supported_actions=tuple(spec.get('supported_actions',['list_favorites']))
        self.implemented=bool(spec.get('implemented',True)); self._capture=spec.get('capture',{})

    def _proxy(self):
        value = self.spec.get('proxy')
        if value is None:
            value = 'auto'
        if isinstance(value, str) and value.strip().lower() == 'auto':
            # 优先使用常见环境变量；Windows 桌面代理再回退到 Internet Settings。
            for key in ('HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy'):
                if os.environ.get(key):
                    return os.environ[key]
            if os.name == 'nt':
                try:
                    import winreg
                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Internet Settings')
                    enabled = winreg.QueryValueEx(key, 'ProxyEnable')[0]
                    server = winreg.QueryValueEx(key, 'ProxyServer')[0]
                    winreg.CloseKey(key)
                    if enabled and server:
                        # 注册表可能返回 http=host:port;https=host:port，优先 HTTPS。
                        parts = dict(p.split('=', 1) for p in str(server).split(';') if '=' in p)
                        server = parts.get('https') or parts.get('http') or server
                        if not str(server).startswith(('http://', 'https://', 'socks5://')):
                            server = 'http://' + str(server)
                        return server
                except (OSError, ImportError, ValueError):
                    pass
            return None
        if isinstance(value, str):
            m = re.fullmatch(r"\$\{([^}]+)\}", value.strip())
            if m: return os.environ.get(m.group(1)) or None
        return value

    def _has_login(self, cookies) -> bool:
        keys = tuple(self.spec.get('login_cookies', []))
        by_name = {str(c.get('name') or '').lower(): c.get('value') for c in cookies or []}
        values = [by_name.get(str(k).lower()) for k in keys]
        if str(self.spec.get('login_cookie_mode', 'any')).lower() == 'all':
            return bool(values) and all(values)
        return any(values)

    @staticmethod
    def _render_url(url: str, account, cookies=None) -> str:
        """渲染声明式 URL 占位符（例如快手主页的 ``{userId}`）。

        userId 优先从当前浏览器 Cookie 读取，也支持 account 属性作为回退。
        未找到值时保留原 URL，避免破坏已有平台配置。
        """
        if not isinstance(url, str) or "{" not in url:
            return url
        values = {"account_id": getattr(account, "account_id", ""),
                  "userId": getattr(account, "userId", "") or ""}
        # 快手个人主页使用 eid（短字符串），而 userId Cookie 是数字账号 ID；
        # 对 {userId} 占位符优先采用 eid，避免导航到错误的数字路径。
        eid_value = ""
        numeric_user_id = ""
        for cookie in cookies or []:
            name, value = cookie.get("name"), cookie.get("value")
            if name == "eid" and value:
                eid_value = value
            elif name == "userId" and value:
                numeric_user_id = value
        if eid_value:
            values["userId"] = eid_value
        elif numeric_user_id:
            values["userId"] = numeric_user_id
        try:
            return url.format_map(values)
        except (KeyError, ValueError):
            return url

    def _script_path(self, value):
        if not value or not self.base_dir: return None
        path = (self.base_dir / value).resolve()
        try: path.relative_to(self.base_dir.resolve())
        except ValueError: raise ValueError('脚本路径必须位于平台目录内')
        return path

    async def _run_hooks(self, phase, page, account, params):
        hooks = self.spec.get('scripts') or {}
        js = hooks.get(f'{phase}_js')
        if js:
            path = self._script_path(js); source = path.read_text(encoding='utf-8')
            await page.evaluate(source, {'account_id': account.account_id, 'params': params})
        py = hooks.get(f'{phase}_python')
        if py:
            path = self._script_path(py)
            proc = await asyncio.create_subprocess_exec(sys.executable, str(path),
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE, cwd=str(self.base_dir))
            payload = json.dumps({'account_id': account.account_id, 'platform': self.platform, 'params': params}, ensure_ascii=False).encode()
            try:
                out, err = await asyncio.wait_for(proc.communicate(payload), timeout=float(hooks.get('python_timeout', 30)))
            except asyncio.TimeoutError:
                proc.kill(); await proc.wait(); raise RuntimeError(f'Python 脚本超时：{path.name}')
            if proc.returncode:
                raise RuntimeError(f'Python 脚本失败：{path.name} ({err.decode(errors="replace")[-500:]})')
            return out.decode(errors='replace')

    async def login(self, account, timeout=None):
        timeout=timeout or config.LOGIN_TIMEOUT; deadline=time.monotonic()+timeout
        async with browser.session(account.profile_path, headless=False, proxy=self._proxy()) as ctx:
            keys=tuple(self.spec.get('login_cookies',[]))
            if self._has_login(await ctx.cookies()):
                return True
            page=ctx.pages[0] if ctx.pages else await ctx.new_page(); await self._run_hooks('before_login', page, account, {}); await page.goto(self.homepage or self.home_url,wait_until='domcontentloaded'); await self._run_hooks('after_login_page', page, account, {})
            while time.monotonic()<deadline:
                if self._has_login(await ctx.cookies()): return True
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
            await self._run_hooks('before_fetch', page, account, params)
            headers = dict(self.spec.get('headers') or {}); headers.update(cap.get('headers') or {})
            # 全局注入自定义头会污染静态脚本请求并触发 CDN CORS 预检。
            # 仅在平台明确声明时启用；页面原生请求通常已带所需头。
            if headers and self.spec.get('apply_headers_globally', False):
                await ctx.set_extra_http_headers({str(k): str(v) for k, v in headers.items()})
            async def on_response(resp):
                nonlocal cursor, has_more
                if cap.get('url_contains') and cap['url_contains'] not in resp.url: return
                try: data=await resp.json()
                except Exception: return
                rows=_walk(data,cap.get('items_path',''))
                cursor = self._value(data, cap.get('cursor_path',''), cursor)
                has_more_value = self._value(data, cap.get('has_more_path',''), has_more)
                # 部分平台（如快手）仅返回字符串游标，末页使用空串或
                # ``no_more`` 等哨兵值表示结束，而非显式布尔字段。
                if isinstance(has_more_value, str):
                    has_more = has_more_value.strip().lower() not in {
                        '', '0', 'false', 'null', 'none', 'no_more', 'nomore', '-1'
                    }
                else:
                    has_more = bool(has_more_value)
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
            page.on('response',on_response); target_url = self._render_url(cap.get('page_url') or self.home_url, account, await ctx.cookies()); await page.goto(target_url,wait_until='domcontentloaded'); await self._run_hooks('after_fetch_page', page, account, params); await page.wait_for_timeout(int(cap.get('wait_ms',3000)))
            for _ in range(max_rounds):
                if (target and len({i['content_id'] for i in batches}) >= target) or (batches and not has_more):
                    break
                await page.mouse.wheel(0, scroll_step)
                await page.wait_for_timeout(int(cap.get('scroll_wait_ms', 1500)))
            if self.spec.get('login_cookies') and not self._has_login(await ctx.cookies()): raise LoginExpiredError(f'{self.display_name} 登录态缺失')
        uniq={i['content_id']:i for i in batches}; items=list(uniq.values()); items=items[:target] if target else items
        return FetchResult(items=items,total=len(items),cursor=cursor,has_more=has_more)
