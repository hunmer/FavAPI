import React, { useState } from 'react';
import { Account, AccountStatus, TaskRecord, ScrapedItem, ScrapingFormData } from '../../types';
import { PLATFORMS } from '../../data/mockFavData';
import {
  ArrowLeft,
  CheckCircle2,
  AlertTriangle,
  Ban,
  QrCode,
  Cookie,
  Monitor,
  Trash2,
  Play,
  FolderSync,
  Clock,
  ExternalLink,
  ShieldCheck,
  Sliders,
  FolderHeart,
  Sparkles,
  RefreshCw,
  Terminal,
} from 'lucide-react';

interface AccountDetailProps {
  account: Account;
  onBack: () => void;
  onOpenLoginModal: (account: Account) => void;
  onOpenCookiesModal: (account: Account) => void;
  onCheckHealth: (account: Account) => void;
  onToggleStatus: (account: Account) => void;
  onToggleBrowser: (account: Account) => void;
  onDeleteAccount: (account: Account) => void;
  recentTasks: TaskRecord[];
  allScrapedItems: ScrapedItem[];
  onTriggerScrape: (formData: ScrapingFormData) => void;
  isScrapingInProgress: boolean;
  streamingItems: ScrapedItem[];
}

export const AccountDetail: React.FC<AccountDetailProps> = ({
  account,
  onBack,
  onOpenLoginModal,
  onOpenCookiesModal,
  onCheckHealth,
  onToggleStatus,
  onToggleBrowser,
  onDeleteAccount,
  recentTasks,
  allScrapedItems,
  onTriggerScrape,
  isScrapingInProgress,
  streamingItems,
}) => {
  const platform = PLATFORMS.find((p) => p.id === account.platform) || PLATFORMS[0];

  // Scraping Form State
  const [count, setCount] = useState<number>(20);
  const [startCursor, setStartCursor] = useState<string>('');
  const [isAsync, setIsAsync] = useState<boolean>(false);
  const [selectedFolderMediaId, setSelectedFolderMediaId] = useState<string>(
    account.folders && account.folders[0] ? account.folders[0].mediaId : ''
  );
  const [customFolderUrlOrUid, setCustomFolderUrlOrUid] = useState<string>('');
  const [pageIntervalSec, setPageIntervalSec] = useState<number>(2.0);
  const [profileUrlOrUid, setProfileUrlOrUid] = useState<string>('');

  // Delete confirm dialog state
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  // Active subtab inside account detail
  const [activeSubTab, setActiveSubTab] = useState<'scrape' | 'tasks' | 'folders'>('scrape');

  const handleStartScraping = (e: React.FormEvent) => {
    e.preventDefault();
    onTriggerScrape({
      count,
      startCursor,
      isAsync,
      mediaId: selectedFolderMediaId,
      folderUrlOrUid: customFolderUrlOrUid,
      pageIntervalSec,
      profileUrlOrUid,
    });
  };

  return (
    <div id="account-detail-view" className="space-y-6">
      {/* Top Bar: Back button & Title */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-2 border-b border-slate-200/80">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onBack}
            className="p-2 rounded-xl bg-white border border-slate-200 text-slate-700 hover:bg-slate-100 transition-colors shadow-2xs"
            title="返回账号列表"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900">
                {account.name}
              </h2>
              <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold border ${platform.badgeBg}`}>
                {platform.name}
              </span>
            </div>
            <p className="text-xs text-slate-500 font-mono mt-0.5">
              Profile: {account.browserProfilePath}
            </p>
          </div>
        </div>

        {/* Action button toolbar */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Health check */}
          <button
            type="button"
            onClick={() => onCheckHealth(account)}
            className="px-3 py-1.5 rounded-xl bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 text-xs font-semibold shadow-2xs inline-flex items-center gap-1.5 transition-colors"
            title="验证当前登录态有效性"
          >
            <ShieldCheck className="w-3.5 h-3.5 text-indigo-600" />
            登录态检查
          </button>

          {/* Re-login */}
          <button
            type="button"
            onClick={() => onOpenLoginModal(account)}
            className="px-3 py-1.5 rounded-xl bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 text-xs font-semibold shadow-2xs inline-flex items-center gap-1.5 transition-colors"
          >
            <QrCode className="w-3.5 h-3.5 text-slate-700" />
            重新扫码
          </button>

          {/* Cookies */}
          <button
            type="button"
            onClick={() => onOpenCookiesModal(account)}
            className="px-3 py-1.5 rounded-xl bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 text-xs font-semibold shadow-2xs inline-flex items-center gap-1.5 transition-colors"
          >
            <Cookie className="w-3.5 h-3.5 text-amber-600" />
            查看 Cookies
          </button>

          {/* Open/Close Browser */}
          <button
            type="button"
            onClick={() => onToggleBrowser(account)}
            className={`px-3 py-1.5 rounded-xl border text-xs font-semibold shadow-2xs inline-flex items-center gap-1.5 transition-colors ${
              account.isBrowserOpen
                ? 'bg-sky-50 border-sky-300 text-sky-800 hover:bg-sky-100'
                : 'bg-white border-slate-200 text-slate-700 hover:bg-slate-50'
            }`}
            title="以该账号独立 Profile 打开/关闭可视化 Chromium 浏览器"
          >
            <Monitor className="w-3.5 h-3.5" />
            {account.isBrowserOpen ? '关闭浏览器' : '打开浏览器'}
          </button>

          {/* Enable / Disable */}
          <button
            type="button"
            onClick={() => onToggleStatus(account)}
            className="px-3 py-1.5 rounded-xl bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 text-xs font-semibold shadow-2xs inline-flex items-center gap-1.5 transition-colors"
          >
            <Ban className="w-3.5 h-3.5 text-slate-500" />
            {account.status === 'disabled' ? '启用账号' : '禁用账号'}
          </button>

          {/* Delete Account */}
          <button
            type="button"
            onClick={() => setShowDeleteConfirm(true)}
            className="p-2 rounded-xl bg-white border border-rose-200 text-rose-600 hover:bg-rose-50 text-xs font-semibold shadow-2xs transition-colors"
            title="删除此账号"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Account Info Cards row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Status card */}
        <div className="bg-white p-4 sm:p-5 rounded-2xl border border-slate-200/80 shadow-2xs">
          <span className="text-xs font-semibold text-slate-500">当前账号状态</span>
          <div className="mt-2 flex items-center justify-between">
            <div>
              {account.status === 'active' ? (
                <span className="inline-flex items-center gap-1.5 text-sm font-bold text-emerald-700">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                  已启用 (登录有效)
                </span>
              ) : account.status === 'expired' ? (
                <span className="inline-flex items-center gap-1.5 text-sm font-bold text-amber-700">
                  <AlertTriangle className="w-4 h-4 text-amber-600" />
                  登录已过期 (需重新扫码)
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 text-sm font-bold text-slate-500">
                  <Ban className="w-4 h-4 text-slate-400" />
                  已禁用
                </span>
              )}
            </div>
            <span className="text-[11px] text-slate-400">ID: {account.id}</span>
          </div>
          <p className="text-[11px] text-slate-400 mt-2">
            最后登录：{account.lastLoginTime}
          </p>
        </div>

        {/* Identity & Owner card */}
        <div className="bg-white p-4 sm:p-5 rounded-2xl border border-slate-200/80 shadow-2xs">
          <span className="text-xs font-semibold text-slate-500">平台主人身份</span>
          <div className="mt-2 flex items-center gap-3">
            {account.ownerAvatar ? (
              <img
                src={account.ownerAvatar}
                alt={account.ownerNickname || ''}
                className="w-10 h-10 rounded-full border-2 border-slate-100 object-cover"
                referrerPolicy="no-referrer"
              />
            ) : (
              <div className="w-10 h-10 rounded-full bg-slate-100 text-slate-600 font-bold flex items-center justify-center text-sm">
                ID
              </div>
            )}
            <div>
              <div className="text-sm font-bold text-slate-900">
                {account.ownerNickname || '未绑定/未登录'}
              </div>
              <div className="text-xs text-slate-500 font-mono">
                UID: {account.ownerUid || '—'}
              </div>
            </div>
          </div>
        </div>

        {/* Usage & Folders card */}
        <div className="bg-white p-4 sm:p-5 rounded-2xl border border-slate-200/80 shadow-2xs">
          <span className="text-xs font-semibold text-slate-500">收藏夹概览</span>
          <div className="mt-2 flex items-center justify-between">
            <span className="text-2xl font-extrabold text-slate-900">
              {account.folders
                ? account.folders.reduce((acc, f) => acc + f.count, 0)
                : 0}
              <span className="text-xs font-normal text-slate-500 ml-1">件收藏内容</span>
            </span>
            <span className="text-xs font-bold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded-full">
              {account.folders?.length || 0} 个收藏夹
            </span>
          </div>
          <p className="text-[11px] text-slate-400 mt-2">
            最近抓取使用：{account.lastUsedTime}
          </p>
        </div>
      </div>

      {/* Bilibili Folders Preview list (if exists) */}
      {account.folders && account.folders.length > 0 && (
        <div className="bg-white p-4 sm:p-5 rounded-2xl border border-slate-200/80 shadow-2xs">
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider flex items-center gap-1.5">
              <FolderHeart className="w-4 h-4 text-indigo-600" />
              名下收藏夹与数量（点击直接设为抓取目标）
            </h4>
            <span className="text-[11px] text-slate-400">自动同步自平台接口</span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2.5">
            {account.folders.map((f) => {
              const isSelected = selectedFolderMediaId === f.mediaId;
              return (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => setSelectedFolderMediaId(f.mediaId)}
                  className={`p-3 rounded-xl border text-left transition-all ${
                    isSelected
                      ? 'border-indigo-600 bg-indigo-50/50 ring-2 ring-indigo-500/20 shadow-2xs'
                      : 'border-slate-200 hover:border-slate-300 hover:bg-slate-50'
                  }`}
                >
                  <div className="flex items-center justify-between text-xs font-bold text-slate-900 mb-1">
                    <span className="truncate">{f.name}</span>
                    {f.isDefault && (
                      <span className="text-[9px] bg-slate-200 text-slate-700 px-1 rounded">默认</span>
                    )}
                  </div>
                  <div className="text-xs text-slate-500 flex items-center justify-between">
                    <span>{f.count} 件</span>
                    <span className="font-mono text-[10px] text-slate-400">ID:{f.mediaId}</span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Main Workspace: Manual Scraping & Recent Tasks Tabs */}
      <div className="bg-white rounded-[28px] border border-slate-200/80 shadow-2xs overflow-hidden">
        {/* Subtab Header */}
        <div className="flex items-center justify-between border-b border-slate-100 px-6 pt-4 pb-1">
          <div className="flex items-center gap-4">
            <button
              type="button"
              onClick={() => setActiveSubTab('scrape')}
              className={`pb-3 text-sm font-bold border-b-2 transition-colors flex items-center gap-1.5 ${
                activeSubTab === 'scrape'
                  ? 'border-slate-900 text-slate-900'
                  : 'border-transparent text-slate-500 hover:text-slate-800'
              }`}
            >
              <Play className="w-4 h-4" />
              手动触发抓取
            </button>
            <button
              type="button"
              onClick={() => setActiveSubTab('tasks')}
              className={`pb-3 text-sm font-bold border-b-2 transition-colors flex items-center gap-1.5 ${
                activeSubTab === 'tasks'
                  ? 'border-slate-900 text-slate-900'
                  : 'border-transparent text-slate-500 hover:text-slate-800'
              }`}
            >
              <Clock className="w-4 h-4" />
              最近任务记录 ({recentTasks.length})
            </button>
          </div>
          <span className="text-xs text-slate-400 hidden sm:inline-block">
            支持 0 抓取全部、游标续抓与反风控间隔调节
          </span>
        </div>

        {/* Tab 1: Manual Scraping Panel */}
        {activeSubTab === 'scrape' && (
          <div className="p-6">
            <form onSubmit={handleStartScraping} className="space-y-6">
              {/* Parameters Grid */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* Count (0 = all) */}
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1.5 uppercase tracking-wider">
                    抓取数量 (0 为全部)
                  </label>
                  <input
                    type="number"
                    min="0"
                    max="1000"
                    value={count}
                    onChange={(e) => setCount(Number(e.target.value))}
                    className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900"
                    placeholder="0 表示抓取全部"
                  />
                  <p className="text-[11px] text-slate-400 mt-1">
                    若设置为 0，结果将以流式方式实时滚动展示。
                  </p>
                </div>

                {/* Start Cursor */}
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1.5 uppercase tracking-wider">
                    起始游标 (Cursor)
                  </label>
                  <input
                    type="text"
                    value={startCursor}
                    onChange={(e) => setStartCursor(e.target.value)}
                    placeholder="留空表示从第 1 条开始"
                    className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900 font-mono text-xs"
                  />
                  <p className="text-[11px] text-slate-400 mt-1">
                    用于翻页续抓，粘贴上次抓取的 Next Cursor。
                  </p>
                </div>

                {/* Async execution toggle */}
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1.5 uppercase tracking-wider">
                    执行模式
                  </label>
                  <div className="flex items-center justify-between p-2.5 rounded-xl border border-slate-200 bg-slate-50/50">
                    <span className="text-xs font-medium text-slate-700">
                      {isAsync ? '后台异步任务 (不阻塞界面)' : '同步流式返回 (实时查看)'}
                    </span>
                    <button
                      type="button"
                      onClick={() => setIsAsync(!isAsync)}
                      className={`w-10 h-5 rounded-full transition-colors relative ${
                        isAsync ? 'bg-slate-900' : 'bg-slate-300'
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
              </div>

              {/* Platform Specific Parameters */}
              {account.platform === 'bilibili' && (
                <div className="bg-slate-50 p-4 sm:p-5 rounded-2xl border border-slate-200/80 space-y-4">
                  <div className="flex items-center gap-2 text-xs font-bold text-slate-800 uppercase tracking-wider">
                    <Sliders className="w-4 h-4 text-indigo-600" />
                    Bilibili 专属高级参数
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
                    <div>
                      <label className="block text-slate-700 font-semibold mb-1">
                        指定收藏夹主页链接或用户 UID
                      </label>
                      <input
                        type="text"
                        value={customFolderUrlOrUid}
                        onChange={(e) => setCustomFolderUrlOrUid(e.target.value)}
                        placeholder="留空则抓当前登录账号"
                        className="w-full px-3 py-2 rounded-xl border border-slate-200 bg-white text-xs focus:outline-none focus:ring-2 focus:ring-slate-900"
                      />
                    </div>

                    <div>
                      <label className="block text-slate-700 font-semibold mb-1">
                        指定单个收藏夹 (media_id)
                      </label>
                      <input
                        type="text"
                        value={selectedFolderMediaId}
                        onChange={(e) => setSelectedFolderMediaId(e.target.value)}
                        placeholder="例如 10082911"
                        className="w-full px-3 py-2 rounded-xl border border-slate-200 bg-white text-xs focus:outline-none focus:ring-2 focus:ring-slate-900 font-mono"
                      />
                    </div>

                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <label className="text-slate-700 font-semibold">
                          翻页休眠间隔 (秒)
                        </label>
                        <span className="font-bold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded">
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
                <div className="bg-slate-50 p-4 rounded-2xl border border-slate-200/80">
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    小红书专属：指定个人主页链接或用户 ID (留空则抓当前登录用户)
                  </label>
                  <input
                    type="text"
                    value={profileUrlOrUid}
                    onChange={(e) => setProfileUrlOrUid(e.target.value)}
                    placeholder="https://www.xiaohongshu.com/user/profile/... 或留空"
                    className="w-full px-3.5 py-2 rounded-xl border border-slate-200 bg-white text-xs focus:outline-none focus:ring-2 focus:ring-slate-900"
                  />
                </div>
              )}

              {/* Submit Trigger Button */}
              <div className="flex items-center justify-between pt-2">
                <div className="text-xs text-slate-500">
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
                  className="px-6 py-2.5 bg-slate-900 hover:bg-slate-800 disabled:opacity-50 text-white rounded-xl text-xs sm:text-sm font-bold shadow-sm inline-flex items-center gap-2 transition-transform active:scale-98"
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

            {/* Real-time Streaming Results Output (抓一条看一条) */}
            {(isScrapingInProgress || streamingItems.length > 0) && (
              <div className="mt-8 pt-6 border-t border-slate-200">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h4 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                      <Terminal className="w-4 h-4 text-emerald-600" />
                      抓取实时反馈流 (已抓取 {streamingItems.length} 条)
                    </h4>
                    <p className="text-xs text-slate-400 mt-0.5">
                      增量入库完成，支持点击标题直接预览原站页面
                    </p>
                  </div>
                  <div className="text-xs font-mono text-slate-500 bg-slate-100 px-3 py-1 rounded-xl">
                    {isScrapingInProgress ? '抓取中...' : '已完成'}
                  </div>
                </div>

                {/* Items stream */}
                <div className="space-y-2.5 max-h-96 overflow-y-auto pr-1">
                  {streamingItems.map((item, idx) => (
                    <div
                      key={item.id + idx}
                      className="p-3 bg-slate-50/80 rounded-xl border border-slate-200/80 flex items-center justify-between gap-3 text-xs hover:bg-slate-100 transition-colors"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        {item.coverUrl ? (
                          <img
                            src={item.coverUrl}
                            alt=""
                            className="w-12 h-8 rounded-lg object-cover bg-slate-200 shrink-0"
                            referrerPolicy="no-referrer"
                          />
                        ) : (
                          <div className="w-12 h-8 rounded-lg bg-slate-200 shrink-0" />
                        )}
                        <div className="min-w-0">
                          <a
                            href={item.url}
                            target="_blank"
                            rel="noreferrer"
                            className="font-semibold text-slate-900 hover:text-indigo-600 truncate block text-xs sm:text-sm"
                          >
                            {item.title}
                          </a>
                          <div className="text-[11px] text-slate-500 flex items-center gap-2 mt-0.5">
                            <span>UP: {item.author}</span>
                            <span>•</span>
                            <span>{item.duration}</span>
                            <span>•</span>
                            <span className="text-slate-400">所属: {item.folderName}</span>
                          </div>
                        </div>
                      </div>

                      <div className="text-right shrink-0">
                        <span className="text-[11px] text-emerald-600 font-bold bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                          新增收藏
                        </span>
                        <div className="text-[10px] text-slate-400 mt-1">{item.favTime}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Tab 2: Recent Tasks List for this Account */}
        {activeSubTab === 'tasks' && (
          <div className="p-6">
            <div className="space-y-3">
              {recentTasks.length > 0 ? (
                recentTasks.map((t) => (
                  <div
                    key={t.id}
                    className="p-4 rounded-2xl border border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs hover:bg-slate-50 transition-colors"
                  >
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-mono font-bold text-slate-900">{t.id}</span>
                        <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 font-semibold">
                          {t.operationType}
                        </span>
                        {t.status === 'success' ? (
                          <span className="text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full font-bold border border-emerald-200">
                            成功
                          </span>
                        ) : t.status === 'running' ? (
                          <span className="text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded-full font-bold border border-indigo-200 flex items-center gap-1">
                            <RefreshCw className="w-3 h-3 animate-spin" /> 进行中
                          </span>
                        ) : (
                          <span className="text-rose-700 bg-rose-50 px-2 py-0.5 rounded-full font-bold border border-rose-200">
                            失败
                          </span>
                        )}
                      </div>
                      <div className="text-slate-500 flex items-center gap-3 text-[11px]">
                        <span>开始时间: {t.startTime}</span>
                        <span>耗时: {t.durationSec}s</span>
                        {t.cursor && <span className="font-mono">游标已保存</span>}
                      </div>
                      {t.errorMessage && (
                        <div className="mt-2 text-rose-600 bg-rose-50 p-2 rounded-xl text-xs">
                          {t.errorMessage}
                        </div>
                      )}
                    </div>

                    <div className="text-right sm:border-l sm:border-slate-100 sm:pl-4">
                      <div className="text-lg font-extrabold text-slate-900">
                        +{t.newCount}
                        <span className="text-xs font-normal text-slate-400 ml-1">/ {t.scrapedCount} 总数</span>
                      </div>
                      <span className="text-[11px] text-slate-400">入库收藏</span>
                    </div>
                  </div>
                ))
              ) : (
                <div className="p-12 text-center text-slate-400 text-xs">
                  暂无抓取任务记录
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="anim-modal-enter bg-white w-full max-w-md rounded-[28px] p-6 shadow-2xl border border-slate-100 space-y-4">
            <h3 className="text-lg font-bold text-slate-900">确认删除账号？</h3>
            <p className="text-xs text-slate-500 leading-relaxed">
              此操作将删除账号 <strong className="text-slate-800">{account.name}</strong> 及其关联的收藏关系与本地 Chromium Profile 目录（{account.browserProfilePath}）。已入库的收藏元数据不会被抹除。
            </p>
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setShowDeleteConfirm(false)}
                className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-800 rounded-xl"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowDeleteConfirm(false);
                  onDeleteAccount(account);
                }}
                className="px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold rounded-xl shadow-xs"
              >
                确认删除
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
