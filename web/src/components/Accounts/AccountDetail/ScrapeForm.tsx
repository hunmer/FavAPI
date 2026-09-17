import React, { useState } from 'react';
import { Account, ScrapingFormData } from '../../../types';
import { PlatformMeta } from '../../../data/platforms';
import { uploadWechatJson } from '../../../api';
import { Play, RefreshCw, Sliders } from 'lucide-react';

interface ScrapeFormProps {
  account: Account;
  platform: PlatformMeta;
  // 与收藏夹预览网格联动：点击卡片即更新抓取目标
  selectedFolderMediaId: string;
  onChangeFolderMediaId: (mediaId: string) => void;
  isScrapingInProgress: boolean;
  onTriggerScrape: (formData: ScrapingFormData) => void;
}

/** 手动抓取表单：通用参数 + Bilibili/小红书/微信平台专属参数 */
export const ScrapeForm: React.FC<ScrapeFormProps> = ({
  account,
  platform,
  selectedFolderMediaId,
  onChangeFolderMediaId,
  isScrapingInProgress,
  onTriggerScrape,
}) => {
  const [count, setCount] = useState<number>(20);
  const [startCursor, setStartCursor] = useState<string>('');
  const [isAsync, setIsAsync] = useState<boolean>(false);
  const [fetchMethod, setFetchMethod] = useState<'browser' | 'api'>('browser');
  const [dateFrom, setDateFrom] = useState<string>('');
  const [dateTo, setDateTo] = useState<string>('');
  const [customFolderUrlOrUid, setCustomFolderUrlOrUid] = useState<string>('');
  const [pageIntervalSec, setPageIntervalSec] = useState<number>(2.0);
  const [profileUrlOrUid, setProfileUrlOrUid] = useState<string>('');
  const [jsonPath, setJsonPath] = useState<string>('');

  const handleStartScraping = (e: React.FormEvent) => {
    e.preventDefault();
    onTriggerScrape({
      count,
      startCursor,
      isAsync,
      method: fetchMethod,
      dateFrom,
      dateTo,
      mediaId: selectedFolderMediaId,
      folderUrlOrUid: customFolderUrlOrUid,
      pageIntervalSec,
      profileUrlOrUid,
      jsonPath,
    });
  };

  return (
    <form onSubmit={handleStartScraping} className="space-y-6">
      {/* Parameters Grid */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {/* Count (0 = all) */}
        <div>
          <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5 uppercase tracking-wider">
            抓取数量 (0 为全部)
          </label>
          <input
            type="number"
            min="0"
            max="1000"
            value={count}
            onChange={(e) => setCount(Number(e.target.value))}
            className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 text-sm bg-transparent dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-slate-900"
            placeholder="0 表示抓取全部"
          />
          <p className="text-[11px] text-slate-400 mt-1">
            若设置为 0，结果将以流式方式实时滚动展示。
          </p>
        </div>

        {/* Start Cursor */}
        <div>
          <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5 uppercase tracking-wider">
            起始游标 (Cursor)
          </label>
          <input
            type="text"
            value={startCursor}
            onChange={(e) => setStartCursor(e.target.value)}
            placeholder="留空表示从第 1 条开始"
            className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 text-sm bg-transparent dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-slate-900 font-mono text-xs"
          />
          <p className="text-[11px] text-slate-400 mt-1">
            用于翻页续抓，粘贴上次抓取的 Next Cursor。
          </p>
        </div>

        {/* Async execution toggle */}
        <div>
          <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5 uppercase tracking-wider">
            执行模式
          </label>
          <div className="flex items-center justify-between p-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-800/60">
            <span className="text-xs font-medium text-slate-700 dark:text-slate-200">
              {isAsync ? '后台异步任务 (不阻塞界面)' : '同步流式返回 (实时查看)'}
            </span>
            <button
              type="button"
              onClick={() => setIsAsync(!isAsync)}
              className={`w-10 h-5 rounded-full transition-colors relative ${
                isAsync ? 'bg-slate-900 dark:bg-slate-600' : 'bg-slate-300 dark:bg-slate-600'
              }`}
            >
              <span
                className={`absolute top-0.5 left-0.5 bg-white w-4 h-4 rounded-full transition-transform ${
                  isAsync ? 'translate-x-5' : ''
                }`}
              />
            </button>
          </div>
          <p className="text-[11px] text-slate-400 mt-1">
            推荐大量抓取时使用异步模式。
          </p>
        </div>

        {/* Fetch method: browser simulation vs direct API */}
        <div>
          <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5 uppercase tracking-wider">
            执行方式
          </label>
          <select
            value={fetchMethod}
            onChange={(e) => setFetchMethod(e.target.value as 'browser' | 'api')}
            className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 text-sm bg-white dark:bg-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-slate-900"
          >
            <option value="browser">浏览器模拟 (兼容性最好)</option>
            {platform.apiFetch && (
              <option value="api">API 请求 (直连，更快)</option>
            )}
          </select>
          <p className="text-[11px] text-slate-400 mt-1">
            {fetchMethod === 'api'
              ? '接口直连抓取，速度快、无需打开浏览器窗口。'
              : '通过 Chromium 会话滚动页面并拦截响应抓取。'}
          </p>
        </div>

        {/* Collected-at date range filter */}
        <div>
          <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5 uppercase tracking-wider">
            收藏日期区间 (可选)
          </label>
          <div className="flex items-center gap-2">
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-xs bg-transparent dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-slate-900"
            />
            <span className="text-slate-400 text-xs shrink-0">至</span>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-xs bg-transparent dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-slate-900"
            />
          </div>
          <p className="text-[11px] text-slate-400 mt-1">
            {(dateFrom || dateTo)
              ? `仅入库 ${dateFrom || '最早'} ~ ${dateTo || '最新'} 的收藏；平台无收藏时间时按发布时间判定。`
              : '留空抓取全部；按收藏时间过滤，缺失时以发布时间兜底。'}
          </p>
        </div>
      </div>

      {/* Platform Specific Parameters */}
      {account.platform === 'bilibili' && (
        <div className="bg-slate-50 dark:bg-slate-800/60 p-4 sm:p-5 rounded-2xl border border-slate-200/80 dark:border-slate-700 space-y-4">
          <div className="flex items-center gap-2 text-xs font-bold text-slate-800 dark:text-slate-200 uppercase tracking-wider">
            <Sliders className="w-4 h-4 text-indigo-600" />
            Bilibili 专属高级参数
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
            <div>
              <label className="block text-slate-700 dark:text-slate-300 font-semibold mb-1">
                指定收藏夹主页链接或用户 UID
              </label>
              <input
                type="text"
                value={customFolderUrlOrUid}
                onChange={(e) => setCustomFolderUrlOrUid(e.target.value)}
                placeholder="留空则抓当前登录账号"
                className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 dark:text-slate-200 text-xs focus:outline-none focus:ring-2 focus:ring-slate-900"
              />
            </div>

            <div>
              <label className="block text-slate-700 dark:text-slate-300 font-semibold mb-1">
                指定单个收藏夹 (media_id)
              </label>
              <input
                type="text"
                value={selectedFolderMediaId}
                onChange={(e) => onChangeFolderMediaId(e.target.value)}
                placeholder="例如 10082911"
                className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 dark:text-slate-200 text-xs focus:outline-none focus:ring-2 focus:ring-slate-900 font-mono"
              />
            </div>

            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="text-slate-700 dark:text-slate-300 font-semibold">
                  翻页休眠间隔 (秒)
                </label>
                <span className="font-bold text-indigo-700 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-950 px-2 py-0.5 rounded">
                  {pageIntervalSec}s
                </span>
              </div>
              <input
                type="range"
                min="1.0"
                max="6.0"
                step="0.5"
                value={pageIntervalSec}
                onChange={(e) => setPageIntervalSec(Number(e.target.value))}
                className="w-full accent-slate-900 cursor-pointer"
              />
              <div className="flex justify-between text-[10px] text-slate-400 mt-0.5">
                <span>快速 (1.0s)</span>
                <span>平稳防风控 (3.0s+)</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {account.platform === 'xiaohongshu' && (
        <div className="bg-slate-50 dark:bg-slate-800/60 p-4 rounded-2xl border border-slate-200/80 dark:border-slate-700">
          <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
            小红书专属：指定个人主页链接或用户 ID (留空则抓当前登录用户)
          </label>
          <input
            type="text"
            value={profileUrlOrUid}
            onChange={(e) => setProfileUrlOrUid(e.target.value)}
            placeholder="https://www.xiaohongshu.com/user/profile/... 或留空"
            className="w-full px-3.5 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 dark:text-slate-200 text-xs focus:outline-none focus:ring-2 focus:ring-slate-900"
          />
        </div>
      )}

      {account.platform === 'wechat' && (
        <div className="bg-slate-50 dark:bg-slate-800/60 p-4 rounded-2xl border border-slate-200/80 dark:border-slate-700">
          <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">微信收藏 JSON 文件路径</label>
          <input type="text" value={jsonPath} onChange={(e) => setJsonPath(e.target.value)}
            placeholder="请先用 WeChatDataAnalysis 导出，再填写 conversations/.../messages.json"
            className="w-full px-3.5 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 dark:text-slate-200 text-xs focus:outline-none focus:ring-2 focus:ring-slate-900" />
          <input id="wechat-json-file" type="file" accept=".json,application/json" className="mt-2 text-xs" onChange={async (e) => {
            const file = e.target.files?.[0]; if (!file) return;
            try { const result = await uploadWechatJson(account.id, file); setJsonPath(result.json_path); }
            catch { /* 上传错误由抓取校验提示 */ }
          }} />
          <button type="button" onClick={() => document.querySelector<HTMLInputElement>('#wechat-json-file')?.click()} className="mt-2 px-3 py-1.5 rounded-lg bg-emerald-600 text-white text-xs font-semibold">导入微信收藏 JSON</button>
          <p className="text-[10px] text-slate-500 dark:text-slate-400 mt-1">导出工具：github.com/LifeArchiveProject/WeChatDataAnalysis；FavAPI 服务需能读取该路径</p>
        </div>
      )}

      {/* Submit Trigger Button */}
      <div className="flex items-center justify-between pt-2">
        <div className="text-xs text-slate-500 dark:text-slate-400">
          {isScrapingInProgress ? (
            <span className="inline-flex items-center gap-1.5 text-indigo-600 font-semibold animate-pulse">
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              正在实时采集数据并解析媒体元信息...
            </span>
          ) : (
            <span>点击开始后将自动调度 Chromium 会话执行抓取</span>
          )}
        </div>

        <button
          type="submit"
          disabled={isScrapingInProgress}
          className="px-6 py-2.5 bg-slate-900 hover:bg-slate-800 dark:bg-slate-700 dark:hover:bg-slate-600 disabled:opacity-50 text-white rounded-xl text-xs sm:text-sm font-bold shadow-sm inline-flex items-center gap-2 transition-transform active:scale-98"
        >
          {isScrapingInProgress ? (
            <>
              <RefreshCw className="w-4 h-4 animate-spin" />
              抓取执行中...
            </>
          ) : (
            <>
              <Play className="w-4 h-4 fill-current" />
              开始抓取收藏
            </>
          )}
        </button>
      </div>
    </form>
  );
};
