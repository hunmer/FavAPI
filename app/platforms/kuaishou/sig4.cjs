// 快手 __NS_hxfalcon 签名生成器（CLI，Node >= 16）。
//
// 用法: echo '{"url":"/rest/v/collect/list","body":{...}}' | node sig4.cjs
//   stdin  : {"url": "<接口 path>", "body": <POST JSON body，GET 传 null>}
//   stdout : 签名字符串（HUDR_...），失败 exit 1 + stderr 错误
//
// 原理：快手 Web 站点对 /rest/v/* 接口启用 __NS_hxfalcon 签名强校验
// （缺失/伪造一律 result=50 签名验证失败，2026-09 实测）。签名由站点 bundle
// (p66-plat.wskwai.com/kos/nlav111422/ks-web/assets/index-*.js) 内的 webpack
// IIFE（内部变量 Jose）生成，剥离后自包含、无外部依赖：
//   Jose.call("$encode", [{url, query:{caver}, form, requestBody}, {suc, err}])
//
// VM 代码在同目录 sig_vm.js；两个实测约束：
//   1. 必须间接 eval（(0, eval)，全局作用域）——模块作用域直接执行 VM 内部报错
//   2. 必须在 stdin end 回调（事件循环内）执行——模块顶层同步 eval 同样报错
//
// 更新方法（签名失效/服务端升级 caver 时）：
//   1. 浏览器打开 www.kuaishou.com，DevTools 定位加载的 index-*.js
//   2. 从 "var Jose = (function" 起按语法边界（CallExpression）截取完整 IIFE
//   3. 整体替换 sig_vm.js 内容（尾部追加 "window.__Jose__ = Jose;"）
const fs = require('fs');
const path = require('path');

globalThis.window = globalThis;
globalThis.document = {
    cookie: '',
    createElement: () => ({ getContext: () => null }),
    referrer: 'https://www.kuaishou.com/',
    location: { href: 'https://www.kuaishou.com/' },
};
globalThis.navigator = {
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36',
    language: 'zh-CN',
    languages: ['zh-CN', 'zh'],
};
globalThis.location = {
    href: 'https://www.kuaishou.com/',
    protocol: 'https:',
    host: 'www.kuaishou.com',
    origin: 'https://www.kuaishou.com',
};

let raw = '';
process.stdin.on('data', (c) => (raw += c));
process.stdin.on('end', () => {
    const { url, body } = JSON.parse(raw);
    const code = fs.readFileSync(path.join(__dirname, 'sig_vm.js'), 'utf-8');
    (0, eval)(code);
    const vm = window.__Jose__;
    const ver = vm.call('$getCatVersion');
    vm.call('$encode', [{
        url,
        query: { caver: String(ver || 2) },
        form: {},
        requestBody: body || {},
    }, {
        suc: (r) => { console.log(r); process.exit(0); },
        err: (e) => { console.error(String(e)); process.exit(1); },
    }]);
});
