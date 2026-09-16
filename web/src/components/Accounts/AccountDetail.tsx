import React, { useState, useEffect } from 'react';
import { Account, AccountStatus, TaskRecord, ScrapedItem, ScrapingFormData } from '../../types';
import { PLATFORMS } from '../../data/mockFavData';
import { uploadWechatJson, clearFavorites, favoriteFacets, listPlatforms, executeOperationStream, OperationStreamEvent, OperationSpec } from '../../api';
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
  MoreVertical,
  Eraser,
  Zap,
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
  onFavoritesCleared?: (account: Account) => void;
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
  onFavoritesCleared,
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
  const [fetchMethod, setFetchMethod] = useState<'browser' | 'api'>('browser');
  const [dateFrom, setDateFrom] = useState<string>('');
  const [dateTo, setDateTo] = useState<string>('');
  const [selectedFolderMediaId, setSelectedFolderMediaId] = useState<string>(
    account.folders && account.folders[0] ? account.folders[0].mediaId : ''
  );
  const [customFolderUrlOrUid, setCustomFolderUrlOrUid] = useState<string>('');
  const [pageIntervalSec, setPageIntervalSec] = useState<number>(2.0);
  const [profileUrlOrUid, setProfileUrlOrUid] = useState<string>('');
  const [jsonPath, setJsonPath] = useState<string>('');

  // Delete confirm dialog state
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  // Platform API operations（功能卡片 + 弹窗表单执行，SSE 流式）
  const [operations, setOperations] = useState<OperationSpec[]>([]);
  const [activeOp, setActiveOp] = useState<OperationSpec | null>(null);
  const [opForm, setOpForm] = useState<Record<string, string>>({});
  const [opRunning, setOpRunning] = useState(false);
  const [opResult, setOpResult] = useState<{ ok: boolean; text: string } | null>(null);
  const [opEvents, setOpEvents] = useState<OperationStreamEvent[]>([]);
  const [showOpDangerConfirm, setShowOpDangerConfirm] = useState(false);

  useEffect(() => {
    setOperations([]);
    listPlatforms()
      .then((rows) => {
        const row = rows.find((r) => r.platform === account.platform);
        setOperations(row?.api_operations || []);
      })
      .catch(() => {/* 拉取失败静默：不显示卡片区 */});
  }, [account.platform]);

  const openOperationModal = (op: OperationSpec) => {
    setActiveOp(op);
    setOpForm(Object.fromEntries(op.params.map((p) => [p.key, ''])));
    setOpResult(null);
    setOpEvents([]);
    setShowOpDangerConfirm(false);
  };

  const describeOpEvent = (ev: OperationStreamEvent): string => {
    switch (ev.type) {
      case 'stage':
        return `拉取收藏列表：第 ${ev.page} 页（本页 ${ev.total_fetched} 条）`;
      case 'progress': {
        // 日期区间管道式取消：带日期位置与累计取消数；ID 列表模式：分批进度
        if (ev.oldest_collected_at) {
          const oldest = ev.oldest_collected_at.slice(0, 10);
          return `第 ${ev.page} 页 · 已翻至 ${oldest} · 本页命中 ${ev.matched_this_page} 条 · 累计取消 ${ev.canceled} 条`;
        }
        return `取消进度：第 ${ev.batch_no}/${ev.total_batches} 批完成（累计 ${ev.done} 条）`;
      }
      case 'done': {
        const r = ev.result || {};
        const pages = r.pages ? `，翻 ${r.pages} 页` : r.batches ? `，共 ${r.batches} 批` : '';
        return `完成：匹配 ${r.matched ?? '-'} 条，已取消 ${r.canceled ?? '-'} 条${pages}`;
      }
      default:
        return '';
    }
  };

  const submitOperation = async () => {
    if (!activeOp) return;
    if (activeOp.danger && !showOpDangerConfirm) {
      setShowOpDangerConfirm(true);
      return;
    }
    setOpRunning(true);
    setOpResult(null);
    setOpEvents([]);
    try {
      const done = await executeOperationStream(account.id, activeOp.op_id, opForm, (ev) => {
        setOpEvents((prev) => [...prev, ev]);
      });
      setOpResult({ ok: true, text: JSON.stringify(done.result ?? done, null, 2) });
    } catch (e) {
      setOpEvents((prev) => [...prev, { type: 'error', message: e instanceof Error ? e.message : String(e) }]);
      setOpResult({ ok: false, text: e instanceof Error ? e.message : String(e) });
    } finally {
      setOpRunning(false);
    }
  };

  // Action menu (dots) & clear-favorites state
  const [showActionMenu, setShowActionMenu] = useState(false);
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [isClearing, setIsClearing] = useState(false);
  const [clearError, setClearError] = useState<string | null>(null);

  // 本地库实时统计（favorites 表按账号聚合），概览卡片与清空确认框使用
  const [localStats, setLocalStats] = useState<{ total: number; folderCount: number } | null>(null);

  const reloadLocalStats = async () => {
    try {
      const facets = await favoriteFacets(account.id);
      setLocalStats({ total: facets.total, folderCount: facets.folders.length });
    } catch {
      /* 统计失败静默，保留上次数值 */
    }
  };

  useEffect(() => {
    setLocalStats(null);
    reloadLocalStats();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [account.id]);

  // Active subtab inside account detail
  const [activeSubTab, setActiveSubTab] = useState<'scrape' | 'tasks' | 'folders'>('scrape');

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

  // 清空本地库中该账号的全部收藏关系（后端一键清空接口）
  const handleClearFavorites = async () => {
    setIsClearing(true);
    setClearError(null);
    try {
      await clearFavorites(account.id);
      setShowClearConfirm(false);
      reloadLocalStats();
      onFavoritesCleared?.(account);
    } catch (e) {
      setClearError(e instanceof Error ? e.message : String(e));
    } finally {
      setIsClearing(false);
    }
  };

  return (
    <div id="account-detail-view" className="space-y-6">
      {/* Top Bar: Back button & Title */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-2 border-b border-slate-200/80">
        <div className="flex items-center gap-3">
          {account.platform !== 'wechat' && <button
            type="button"
            onClick={onBack}
            className="p-2 rounded-xl bg-white border border-slate-200 text-slate-700 hover:bg-slate-100 transition-colors shadow-2xs"
            title="返回账号列表"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>}
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
          {account.platform !== 'wechat' && <button
            type="button"
            onClick={() => onCheckHealth(account)}
            className="px-3 py-1.5 rounded-xl bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 text-xs font-semibold shadow-2xs inline-flex items-center gap-1.5 transition-colors"
            title="验证当前登录态有效性"
          >
            <ShieldCheck className="w-3.5 h-3.5 text-indigo-600" />
            登录态检查
          </button>}

          {/* Re-login */}
          {account.platform !== 'wechat' && <button
            type="button"
            onClick={() => onOpenLoginModal(account)}
            className="px-3 py-1.5 rounded-xl bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 text-xs font-semibold shadow-2xs inline-flex items-center gap-1.5 transition-colors"
          >
            <QrCode className="w-3.5 h-3.5 text-slate-700" />
            重新扫码
          </button>}

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
              'bg-white border-slate-200 text-slate-700 hover:bg-slate-50'
            }`}
            title="以该账号独立 Profile 打开/关闭可视化 Chromium 浏览器"
          >
            <Monitor className="w-3.5 h-3.5" />
            打开浏览器
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

          {/* More actions menu (dots) */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setShowActionMenu((v) => !v)}
              className="p-2 rounded-xl bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 shadow-2xs transition-colors"
              title="更多操作"
            >
              <MoreVertical className="w-3.5 h-3.5" />
            </button>

            {showActionMenu && (
              <>
                <div className="fixed inset-0 z-40" onClick={() => setShowActionMenu(false)} />
                <div className="absolute right-0 mt-2 w-44 bg-white rounded-2xl shadow-xl border border-slate-200 py-1.5 z-50 anim-modal-enter">
                  <button
                    type="button"
                    onClick={() => {
                      setShowActionMenu(false);
                      setClearError(null);
                      setShowClearConfirm(true);
                    }}
                    className="w-full px-4 py-2 text-left text-xs font-semibold text-slate-700 hover:bg-slate-50 inline-flex items-center gap-2 transition-colors"
                  >
                    <Eraser className="w-3.5 h-3.5 text-amber-600" />
                    清空收藏夹
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setShowActionMenu(false);
                      setShowDeleteConfirm(true);
                    }}
                    className="w-full px-4 py-2 text-left text-xs font-semibold text-rose-600 hover:bg-rose-50 inline-flex items-center gap-2 transition-colors"
                  >
                    <Trash2 className="w-3.5 h-3.5 text-rose-500" />
                    删除账号
                  </button>
                </div>
              </>
            )}
          </div>
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
              {localStats
                ? localStats.total
                : account.folders
                  ? account.folders.reduce((acc, f) => acc + f.count, 0)
                  : 0}
              <span className="text-xs font-normal text-slate-500 ml-1">件收藏内容（本地库）</span>
            </span>
            <span className="text-xs font-bold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded-full">
              {localStats ? localStats.folderCount : account.folders?.length || 0} 个收藏夹
            </span>
          </div>
          <p className="text-[11px] text-slate-400 mt-2">
            最近抓取使用：{account.lastUsedTime}
          </p>
        </div>
      </div>

      {/* Platform API Operations cards */}
      {operations.length > 0 && (
        <div className="bg-white p-4 sm:p-5 rounded-2xl border border-slate-200/80 shadow-2xs">
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider flex items-center gap-1.5">
              <Zap className="w-4 h-4 text-amber-500" />
              平台 API 操作
            </h4>
            <span className="text-[11px] text-slate-400">点击卡片填写参数后执行</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
            {operations.map((op) => (
              <button
                key={op.op_id}
                type="button"
                onClick={() => openOperationModal(op)}
                className={`p-3 rounded-xl border text-left transition-all ${
                  op.danger
                    ? 'border-rose-200 hover:border-rose-300 hover:bg-rose-50/50'
                    : 'border-slate-200 hover:border-slate-300 hover:bg-slate-50'
                }`}
              >
                <div className="flex items-center justify-between text-xs font-bold mb-1">
                  <span className={op.danger ? 'text-rose-700' : 'text-slate-900'}>{op.name}</span>
                  {op.danger && (
                    <span className="text-[9px] bg-rose-100 text-rose-600 px-1.5 py-0.5 rounded font-semibold">
                      危险操作
                    </span>
                  )}
                </div>
                <div className="text-[11px] text-slate-500 leading-snug line-clamp-2">
                  {op.description}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

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
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
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

                {/* Fetch method: browser simulation vs direct API */}
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1.5 uppercase tracking-wider">
                    执行方式
                  </label>
                  <select
                    value={fetchMethod}
                    onChange={(e) => setFetchMethod(e.target.value as 'browser' | 'api')}
                    className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-slate-900"
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
                  <label className="block text-xs font-bold text-slate-700 mb-1.5 uppercase tracking-wider">
                    收藏日期区间 (可选)
                  </label>
                  <div className="flex items-center gap-2">
                    <input
                      type="date"
                      value={dateFrom}
                      onChange={(e) => setDateFrom(e.target.value)}
                      className="w-full px-3 py-2 rounded-xl border border-slate-200 text-xs focus:outline-none focus:ring-2 focus:ring-slate-900"
                    />
                    <span className="text-slate-400 text-xs shrink-0">至</span>
                    <input
                      type="date"
                      value={dateTo}
                      onChange={(e) => setDateTo(e.target.value)}
                      className="w-full px-3 py-2 rounded-xl border border-slate-200 text-xs focus:outline-none focus:ring-2 focus:ring-slate-900"
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

              {account.platform === 'wechat' && (
                <div className="bg-slate-50 p-4 rounded-2xl border border-slate-200/80">
                  <label className="block text-xs font-semibold text-slate-700 mb-1">微信收藏 JSON 文件路径</label>
                  <input type="text" value={jsonPath} onChange={(e) => setJsonPath(e.target.value)}
                    placeholder="请先用 WeChatDataAnalysis 导出，再填写 conversations/.../messages.json"
                    className="w-full px-3.5 py-2 rounded-xl border border-slate-200 bg-white text-xs focus:outline-none focus:ring-2 focus:ring-slate-900" />
                  <input id="wechat-json-file" type="file" accept=".json,application/json" className="mt-2 text-xs" onChange={async (e) => {
                    const file = e.target.files?.[0]; if (!file) return;
                    try { const result = await uploadWechatJson(account.id, file); setJsonPath(result.json_path); }
                    catch { /* 上传错误由抓取校验提示 */ }
                  }} />
                  <button type="button" onClick={() => document.querySelector<HTMLInputElement>('#wechat-json-file')?.click()} className="mt-2 px-3 py-1.5 rounded-lg bg-emerald-600 text-white text-xs font-semibold">导入微信收藏 JSON</button>
                  <p className="text-[10px] text-slate-500 mt-1">导出工具：github.com/LifeArchiveProject/WeChatDataAnalysis；FavAPI 服务需能读取该路径</p>
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

      {/* Clear Favorites Confirmation Modal */}
      {showClearConfirm && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="anim-modal-enter bg-white w-full max-w-md rounded-[28px] p-6 shadow-2xl border border-slate-100 space-y-4">
            <h3 className="text-lg font-bold text-slate-900">确认清空收藏夹？</h3>
            <p className="text-xs text-slate-500 leading-relaxed">
              将删除 <strong className="text-slate-800">{account.name}</strong> 在本地库中的全部收藏关系（共{' '}
              {localStats ? localStats.total : 0} 件）。平台云端收藏不受影响，可随时重新抓取恢复。
            </p>
            {clearError && (
              <p className="text-xs text-rose-600 bg-rose-50 p-2 rounded-xl">{clearError}</p>
            )}
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                disabled={isClearing}
                onClick={() => setShowClearConfirm(false)}
                className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-800 rounded-xl disabled:opacity-50"
              >
                取消
              </button>
              <button
                type="button"
                disabled={isClearing}
                onClick={handleClearFavorites}
                className="px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white text-xs font-bold rounded-xl shadow-xs disabled:opacity-50 inline-flex items-center gap-1.5"
              >
                {isClearing && <RefreshCw className="w-3 h-3 animate-spin" />}
                {isClearing ? '清空中...' : '确认清空'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* API Operation Execute Modal */}
      {activeOp && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="anim-modal-enter bg-white w-full max-w-md rounded-[28px] p-6 shadow-2xl border border-slate-100 space-y-4 max-h-[85vh] overflow-y-auto">
            <div>
              <h3 className="text-lg font-bold text-slate-900 flex items-center gap-2">
                {activeOp.name}
                {activeOp.danger && (
                  <span className="text-[10px] bg-rose-100 text-rose-600 px-2 py-0.5 rounded-full font-semibold">
                    危险操作
                  </span>
                )}
              </h3>
              {activeOp.description && (
                <p className="text-xs text-slate-500 mt-1">{activeOp.description}</p>
              )}
            </div>

            {activeOp.params.map((p) => (
              <div key={p.key}>
                <label className="block text-xs font-bold text-slate-700 mb-1.5">
                  {p.label}
                  {p.required && <span className="text-rose-500 ml-0.5">*</span>}
                </label>
                {p.type === 'textarea' ? (
                  <textarea
                    value={opForm[p.key] || ''}
                    onChange={(e) => setOpForm((f) => ({ ...f, [p.key]: e.target.value }))}
                    placeholder={p.placeholder}
                    rows={5}
                    className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-slate-900"
                  />
                ) : (
                  <input
                    type={p.type === 'number' ? 'number' : p.type === 'date' ? 'date' : 'text'}
                    value={opForm[p.key] || ''}
                    onChange={(e) => setOpForm((f) => ({ ...f, [p.key]: e.target.value }))}
                    placeholder={p.placeholder}
                    className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900"
                  />
                )}
                {p.help && <p className="text-[11px] text-slate-400 mt-1">{p.help}</p>}
              </div>
            ))}

            {showOpDangerConfirm && (
              <p className="text-xs text-rose-700 bg-rose-50 border border-rose-200 p-3 rounded-xl flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                该操作不可恢复！再次点击「确认执行」将真正提交到平台。
              </p>
            )}

            {(opRunning || opEvents.length > 0) && (
              <div className="rounded-xl border border-slate-200 bg-slate-950 p-3 max-h-44 overflow-y-auto space-y-1">
                <div className="text-[10px] font-mono text-slate-500 uppercase tracking-wider mb-1">
                  实时执行日志 {opRunning && <span className="animate-pulse">▍</span>}
                </div>
                {opEvents.map((ev, i) => (
                  <div
                    key={i}
                    className={`text-[11px] font-mono leading-relaxed ${
                      ev.type === 'error'
                        ? 'text-rose-400'
                        : ev.type === 'done'
                          ? 'text-emerald-400'
                          : ev.type === 'matched'
                            ? 'text-amber-300'
                            : 'text-slate-300'
                    }`}
                  >
                    {ev.type === 'error' ? `✗ ${ev.message}` : describeOpEvent(ev)}
                  </div>
                ))}
              </div>
            )}

            {opResult && (
              <pre
                className={`text-[11px] font-mono p-3 rounded-xl max-h-40 overflow-auto whitespace-pre-wrap ${
                  opResult.ok
                    ? 'bg-emerald-50 text-emerald-800 border border-emerald-200'
                    : 'bg-rose-50 text-rose-700 border border-rose-200'
                }`}
              >
                {opResult.text}
              </pre>
            )}

            <div className="flex justify-end gap-2 pt-1">
              <button
                type="button"
                disabled={opRunning}
                onClick={() => setActiveOp(null)}
                className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-800 rounded-xl disabled:opacity-50"
              >
                关闭
              </button>
              <button
                type="button"
                disabled={opRunning || (activeOp.params.some((p) => p.required) && activeOp.params.some((p) => p.required && !(opForm[p.key] || '').trim()))}
                onClick={submitOperation}
                className={`px-5 py-2 text-xs font-bold text-white rounded-xl shadow-xs disabled:opacity-50 inline-flex items-center gap-1.5 ${
                  activeOp.danger
                    ? 'bg-rose-600 hover:bg-rose-700'
                    : 'bg-slate-900 hover:bg-slate-800'
                }`}
              >
                {opRunning && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                {opRunning
                  ? '执行中...'
                  : showOpDangerConfirm
                    ? '确认执行'
                    : '执行'}
              </button>
            </div>
          </div>
        </div>
      )}

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
