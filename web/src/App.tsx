import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import {
  Account,
  PlatformId,
  NavTab,
  ScrapedItem,
  ScrapingFormData,
  TaskRecord,
  ScheduledSync,
} from './types';
import { PLATFORMS } from './data/platforms';
import * as api from './api';
import { Sidebar } from './components/Sidebar';
import { Header } from './components/Header';
import { DashboardView } from './components/Dashboard/DashboardView';
import { AccountsList } from './components/Accounts/AccountsList';
import { AccountDetail } from './components/Accounts/AccountDetail';
import { CreateAccountModal } from './components/Accounts/CreateAccountModal';
import { QRCodeLoginModal } from './components/Accounts/QRCodeLoginModal';
import { CookiesModal } from './components/Accounts/CookiesModal';
import { TasksView } from './components/Tasks/TasksView';
import { DataBrowserView } from './components/Data/DataBrowserView';
import { ScheduleView } from './components/Schedule/ScheduleView';
import { DownloadsView } from './components/Downloads/DownloadsView';
import { SettingsView } from './components/Settings/SettingsView';
import { CheckCircle2, AlertCircle, Info } from 'lucide-react';
import { DevInspector } from './components/DevInspector';
import { AnimatePresence, motion } from 'motion/react';
import { useLocation, useNavigate, useNavigationType } from 'react-router-dom';

// 视图切换缓动（motion-design 规范）：入场 MD3 Emphasized 减速 / 出场 MD3 Accelerate 加速
// 入场 400ms > 出场 200ms（Enter 比 Exit 长 30-50%），总时长落在页面过渡 400-600ms 区间
const VIEW_EASE_IN: [number, number, number, number] = [0.05, 0.7, 0.1, 1];
const VIEW_EASE_OUT: [number, number, number, number] = [0.3, 0, 1, 1];

export function App() {
  // Theme State
  const [theme, setTheme] = useState<'light' | 'dark'>('light');

  // Page Layout：全屏铺满 / 居中卡片窗口（localStorage 持久化）
  const [fullPage, setFullPage] = useState(() => localStorage.getItem('favapi_fullpage') === '1');
  const setFullPageAndSave = (v: boolean) => {
    setFullPage(v);
    localStorage.setItem('favapi_fullpage', v ? '1' : '0');
  };

  // Avatar State（后端已上传的自定义头像，null 时用默认图）
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null);

  const toggleTheme = () => {
    setTheme((prev) => (prev === 'light' ? 'dark' : 'light'));
  };

  // Navigation State：由 URL hash 驱动（/#/data 等），未知路径回落 dashboard
  const NAV_TABS: NavTab[] = ['dashboard', 'accounts', 'data', 'tasks', 'schedule', 'downloads', 'settings'];
  const location = useLocation();
  const navigate = useNavigate();
  const pathTab = location.pathname.replace(/^\//, '').split('/')[0] as NavTab;
  const activeTab = NAV_TABS.includes(pathTab) ? pathTab : 'dashboard';
  const setActiveTab = (tab: NavTab) => navigate(`/${tab}`);
  const [selectedAccount, setSelectedAccount] = useState<Account | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  // Core Data State（全部来自后端 /api/v1）
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  const [scrapedItems, setScrapedItems] = useState<ScrapedItem[]>([]);
  const [schedules, setSchedules] = useState<ScheduledSync[]>([]);
  const [agents, setAgents] = useState<api.AgentConfigRow[]>([]);
  const [tagStats, setTagStats] = useState<api.TagStatRow[]>([]);
  const [tagGroups, setTagGroups] = useState<api.TagGroupRow[]>([]);
  const [stats, setStats] = useState<api.StatsData | null>(null);
  const [browserOpenIds, setBrowserOpenIds] = useState<Set<string>>(new Set());

  // 选中账号 ↔ URL ?account= 同步：UI 操作时 push 写入（后退键可退回列表），
  // 浏览器 POP 导航（后退/前进/手动改 hash/刷新）时以 URL 为准反推选中态
  const openAccountDetail = useCallback(
    (acc: Account) => {
      setSelectedAccount(acc);
      navigate(`/accounts?account=${encodeURIComponent(acc.id)}`);
    },
    [navigate]
  );

  const closeAccountDetail = useCallback(() => {
    setSelectedAccount(null);
    if (location.pathname.startsWith('/accounts')) navigate('/accounts');
  }, [navigate, location.pathname]);

  // 浏览器后退/前进（POP）或刷新加载：按 URL ?account= 恢复选中账号
  const navigationType = useNavigationType();
  useEffect(() => {
    if (navigationType !== 'POP' || activeTab !== 'accounts') return;
    const urlAccountId = new URLSearchParams(location.search).get('account');
    const next = urlAccountId ? accounts.find((a) => a.id === urlAccountId) ?? null : null;
    if ((selectedAccount?.id ?? null) !== (next?.id ?? null)) setSelectedAccount(next);
  }, [navigationType, activeTab, location.search, accounts, selectedAccount]);

  // Modals State
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [loginModalAccount, setLoginModalAccount] = useState<Account | null>(null);
  const [cookiesModalAccount, setCookiesModalAccount] = useState<Account | null>(null);

  // 抓取进度状态：按账号隔离（实时反馈流每个账号独立，互不串扰）
  const [streamingByAccount, setStreamingByAccount] = useState<Record<string, ScrapedItem[]>>({});
  const [scrapingAccountIds, setScrapingAccountIds] = useState<Set<string>>(new Set());

  const markScraping = (accountId: string, running: boolean) =>
    setScrapingAccountIds((prev) => {
      const next = new Set(prev);
      if (running) next.add(accountId);
      else next.delete(accountId);
      return next;
    });

  // Toast Notification State
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'info' | 'error' } | null>(null);
  const toastTimer = useRef<number | undefined>(undefined);

  const showToast = (message: string, type: 'success' | 'info' | 'error' = 'success') => {
    setToast({ message, type });
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(null), type === 'error' ? 6000 : 3500);
  };

  // ---------- 数据加载 ----------

  const accountNameById = useCallback(
    () => new Map(accounts.map((a) => [a.id, a.name])),
    [accounts]
  );

  const reloadAccounts = useCallback(async (): Promise<Map<string, string>> => {
    try {
      const rows = await api.listAccounts();
      const mapped = rows.map((r) => api.toAccount(r, browserOpenIds));
      setAccounts(mapped);
      setSelectedAccount((prev) => (prev ? mapped.find((a) => a.id === prev.id) || null : null));
      return new Map(mapped.map((a) => [a.id, a.name] as [string, string]));
    } catch (e: any) {
      showToast(`账号列表加载失败：${e.message}`, 'error');
      return new Map();
    }
  }, [browserOpenIds]);

  const reloadTasks = useCallback(async (nameMap?: Map<string, string>) => {
    try {
      const rows = await api.listTasks(100);
      const map = nameMap || accountNameById();
      setTasks(rows.map((r) => api.toTask(r, map)));
    } catch {
      /* 任务列表轮询失败静默，下一轮重试 */
    }
  }, [accountNameById]);

  const reloadFavorites = useCallback(async (nameMap?: Map<string, string>) => {
    try {
    const { items } = await api.listFavorites({ limit: 5000 });
      const map = nameMap || accountNameById();
      setScrapedItems(items.map((r) => api.toScrapedItem(r, map)));
    } catch {
      /* 数据加载失败静默 */
    }
  }, [accountNameById]);

  const reloadSchedules = useCallback(async (nameMap?: Map<string, string>) => {
    try {
      const rows = await api.listSchedules();
      const map = nameMap || accountNameById();
      setSchedules(rows.map((r) => api.toSchedule(r, map)));
    } catch {
      /* 静默 */
    }
  }, [accountNameById]);

  const reloadStats = useCallback(async () => {
    try {
      setStats(await api.getStats());
    } catch {
      /* 静默 */
    }
  }, []);

  const reloadAgents = useCallback(async (): Promise<api.AgentConfigRow[]> => {
    try {
      const rows = await api.listAgents();
      setAgents(rows);
      return rows;
    } catch {
      /* 静默 */
      return [];
    }
  }, []);

  const reloadTags = useCallback(async () => {
    try {
      const { tags, groups } = await api.listTags();
      setTagStats(tags);
      setTagGroups(groups);
    } catch {
      /* 静默 */
    }
  }, []);

  // 初始加载：平台支持情况 + 各类数据 + 手动浏览窗口状态
  useEffect(() => {
    (async () => {
      // 自定义头像（未上传时静默回退默认图）
      api.fetchAvatarUrl().then(setAvatarUrl).catch(() => {});
      try {
        const infos = await api.listPlatforms();
        const implemented = new Set(infos.filter((i) => i.implemented).map((i) => i.platform));
        PLATFORMS.forEach((p) => {
          p.isSupported = implemented.has(p.id);
        });
        // 后端热加载平台（如 threads）不在静态列表中，动态追加
        const known = new Set(PLATFORMS.map((p) => p.id));
        for (const info of infos) {
          if (known.has(info.platform)) continue;
          PLATFORMS.push({
            id: info.platform,
            name: info.display_name,
            icon: '',
            color: '#64748B',
            badgeBg: 'bg-slate-100 text-slate-600 border-slate-200',
            isSupported: info.implemented,
            tagline: '',
            apiFetch: !!info.api_fetch_implemented,
          });
        }
      } catch {
        /* 后端不可用时保持静态标记 */
      }

      const nameMap = await reloadAccounts();
      await Promise.all([reloadTasks(nameMap), reloadFavorites(nameMap), reloadSchedules(nameMap), reloadStats(), reloadAgents(), reloadTags()]);

      // 恢复各账号手动浏览窗口的打开状态
      try {
        const rows = await api.listAccounts();
        const open = new Set<string>();
        for (const r of rows) {
          try {
            const s = await api.browseStatus(r.account_id);
            if (s.opened) open.add(r.account_id);
          } catch { /* ignore */ }
        }
        setBrowserOpenIds(open);
      } catch { /* ignore */ }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---------- 账号操作 ----------

  const handleCreateAccount = async (name: string, platform: PlatformId) => {
    try {
      const row = await api.createAccount(platform, name);
      showToast(`成功创建账号「${row.name}」，Profile 隔离目录已就绪！`);
      reloadAccounts();
    } catch (e: any) {
      showToast(e.message, 'error');
    }
  };

  const handleLoginDone = (accountId: string, ok: boolean) => {
    reloadAccounts().then((map) => reloadTasks(map));
    showToast(ok ? '扫码登录成功！已自动存库最新 Cookies' : '未检测到登录态（超时或未扫码）', ok ? 'success' : 'error');
  };

  const handleQuickCheckHealth = async (account: Account) => {
    showToast(`正在验证「${account.name}」的当前会话 Cookies 有效性...`, 'info');
    try {
      const s = await api.loginStatus(account.id);
      if (s.logged_in === null) {
        showToast(`「${account.name}」浏览器正被占用，稍后再试`, 'error');
      } else if (s.logged_in) {
        showToast(`「${account.name}」登录态有效（${s.status}）`, 'success');
      } else {
        showToast(`「${account.name}」登录态已过期（${s.status}），请重新扫码`, 'error');
        setLoginModalAccount(account);
      }
      reloadAccounts();
    } catch (e: any) {
      showToast(e.message, 'error');
    }
  };

  const handleRefreshProfile = async (account: Account) => {
    try {
      await api.refreshProfile(account.id);
      showToast(`已刷新「${account.name}」账号信息`, 'success');
      await reloadAccounts();
    } catch (e: any) {
      showToast(e.message, 'error');
    }
  };

  const handleToggleStatus = async (account: Account) => {
    const next = account.status === 'disabled' ? 'active' : 'disabled';
    try {
      await api.patchAccount(account.id, { status: next });
      showToast(`账号已切换为「${next === 'active' ? '已启用' : '已禁用'}」`);
      reloadAccounts();
    } catch (e: any) {
      showToast(e.message, 'error');
    }
  };

  const handleToggleBrowser = async (account: Account) => {
    try {
      const res = await api.toggleBrowse(account.id);
      const open = new Set(browserOpenIds);
      if (res.opened) open.add(account.id);
      else open.delete(account.id);
      setBrowserOpenIds(open);
      setSelectedAccount((prev) => (prev && prev.id === account.id ? { ...prev, isBrowserOpen: !!res.opened } : prev));
      showToast(res.opened ? `已通过隔离 Profile 启动可视浏览器窗口` : '已安全关闭浏览器窗口');
    } catch (e: any) {
      showToast(e.message, 'error');
    }
  };

  const handleDeleteAccount = async (account: Account) => {
    try {
      await api.deleteAccount(account.id);
      if (selectedAccount?.id === account.id) closeAccountDetail();
      showToast(`已删除账号「${account.name}」及其浏览器 Profile`);
      reloadAccounts().then((map) => {
        reloadFavorites(map);
        reloadSchedules(map);
      });
    } catch (e: any) {
      showToast(e.message, 'error');
    }
  };

  /** 批量刷新账号身份信息；结果 toast 由这里统一提示，组件只管 loading。 */
  const handleRefreshProfiles = async (): Promise<api.RefreshProfilesResult> => {
    let res: api.RefreshProfilesResult;
    try {
      res = await api.refreshProfiles();
    } catch (e: any) {
      showToast(`身份信息刷新失败：${e.message}`, 'error');
      throw e;
    }
    await reloadAccounts();
    const skipped = res.results.filter((r) => r.status === 'skipped').length;
    const failedNames = res.results.filter((r) => r.status === 'failed').map((r) => r.name);
    if (res.failed > 0) {
      showToast(`刷新完成：成功 ${res.ok}，失败 ${res.failed}（${failedNames.join('、')}），详见服务日志`, 'error');
    } else {
      showToast(`刷新完成：成功 ${res.ok} 个${skipped ? `，${skipped} 个平台暂不支持` : ''}`);
    }
    return res;
  };

  // ---------- 抓取 ----------

  const applyStreamItem = (
    it: NonNullable<api.StreamEvent['items']>[number],
    account: Account,
    folderFallback?: string
  ): ScrapedItem => ({
    id: it.content_id,
    title: it.title || it.content_id,
    url: it.url || '#',
    author: it.author_name || '—',
    duration: it.duration ? `${Math.floor(it.duration / 60)}:${String(it.duration % 60).padStart(2, '0')}` : undefined,
    likes: 0,
    favorites: 0,
    folderName: it.fav_title || folderFallback || '默认收藏夹',
    favTime: (it.collected_at || '').replace('T', ' ').slice(0, 19),
    crawlTime: new Date().toISOString().replace('T', ' ').slice(0, 19),
    coverUrl: it.cover_url || '',
    platform: account.platform,
    accountId: account.id,
    accountName: account.name,
  });

  const handleTriggerScrape = async (formData: ScrapingFormData) => {
    const account = selectedAccount;
    if (!account) return;
    const accId = account.id;
    markScraping(accId, true);
    setStreamingByAccount((prev) => ({ ...prev, [accId]: [] }));
    showToast(`已发起针对「${account.name}」的收藏抓取任务`, 'info');

    try {
      if (formData.isAsync) {
        // 后台异步：立即返回 task_id，轮询任务状态
        const res = await api.fetchAsync(account.platform, account.id, formData);
        showToast(`任务已提交（${res.task_id}），可稍后在任务记录查看结果`);
        const poll = window.setInterval(async () => {
          try {
            const t = await api.getTask(res.task_id);
            if (t.status === 'success' || t.status === 'failed') {
              window.clearInterval(poll);
              markScraping(accId, false);
              if (t.status === 'failed') showToast(t.error_message || '抓取失败', 'error');
              else showToast(`抓取完成！本次入库 ${t.result_count ?? 0} 条`);
              const map = await reloadAccounts();
              reloadTasks(map);
              reloadFavorites(map);
            }
          } catch {
            window.clearInterval(poll);
            markScraping(accId, false);
          }
        }, 3000);
      } else {
        // 同步 SSE 流式：逐批实时展示（写入该账号自己的反馈流）
        const done = await api.fetchStream(account.platform, account.id, formData, (ev) => {
          if (ev.type === 'items' && ev.items) {
            const mapped = ev.items.map((it) => applyStreamItem(it, account, ev.folder));
            setStreamingByAccount((prev) => ({
              ...prev,
              [accId]: [...mapped.reverse(), ...(prev[accId] || [])],
            }));
          }
        });
        showToast(`抓取完成！共入库 ${done.result_count ?? 0} 条（新增 ${done.new_favorites ?? 0}）`);
        markScraping(accId, false);
        const map = await reloadAccounts();
        reloadTasks(map);
        reloadFavorites(map);
      }
    } catch (e: any) {
      markScraping(accId, false);
      showToast(e.message, 'error');
    }
  };

  // ---------- 定时任务 ----------

  // Header 抓取进度：本地发起的抓取 ∪ 后端 running 任务的账号并集
  const runningFetch = useMemo(() => {
    const ids = new Set(scrapingAccountIds);
    tasks.forEach((t) => {
      if (t.status === 'running' && t.accountId) ids.add(t.accountId);
    });
    const names = accounts.filter((a) => ids.has(a.id)).map((a) => a.name);
    const liveCount = Object.values<ScrapedItem[]>(streamingByAccount).reduce((n, arr) => n + arr.length, 0);
    return { count: ids.size, accountNames: names, liveCount };
  }, [scrapingAccountIds, tasks, accounts, streamingByAccount]);

  const handleTriggerSchedule = async (sched: ScheduledSync) => {
    showToast(`已立即触发计划「${sched.title}」，正在后台执行...`, 'info');
    try {
      const res = await api.triggerSchedule(sched.id);
      if ((res as any).skipped) showToast(`计划「${sched.title}」上一轮任务尚未结束，已跳过`, 'error');
      else showToast(`计划「${sched.title}」已触发任务 ${(res as any).task_id}`, 'success');
      reloadAccounts().then((map) => {
        reloadTasks(map);
        reloadSchedules(map);
      });
    } catch (e: any) {
      showToast(e.message, 'error');
    }
  };

  const handleToggleSchedule = async (scheduleId: string) => {
    const sched = schedules.find((s) => s.id === scheduleId);
    if (!sched) return;
    const next = sched.status === 'active' ? 'paused' : 'active';
    try {
      await api.updateSchedule(scheduleId, { status: next });
      showToast(`已${next === 'active' ? '启用' : '暂停'}计划「${sched.title}」`);
      reloadSchedules();
    } catch (e: any) {
      showToast(e.message, 'error');
    }
  };

  const handleCreateSchedule = async (body: {
    action: 'list_favorites' | 'ai_tag';
    account_id: string;
    cron_expr: string;
    title: string;
    count: number;
    platform: string;
    agentId: string;
    limit: number;
  }) => {
    if (body.action === 'ai_tag') {
      await api.createSchedule({
        cron_expr: body.cron_expr,
        title: body.title,
        action: 'ai_tag',
        platform: body.platform,
        params: { agent_id: body.agentId, platform: body.platform, limit: body.limit },
      });
    } else {
      await api.createSchedule({
        account_id: body.account_id,
        cron_expr: body.cron_expr,
        title: body.title,
        params: body.count > 0 ? { count: body.count } : {},
      });
    }
    showToast(`定时计划「${body.title}」创建成功`);
    reloadSchedules();
  };

  const handleCreateAgent = async (agentBody: { name: string; base_url: string; api_key: string; model_id: string }) => {
    const created = await api.createAgent(agentBody);
    await reloadAgents();
    showToast(`AI Agent 配置「${created.name}」已保存`);
    return created;
  };

  const handleUpdateAgent = async (
    id: string,
    body: { name: string; base_url: string; api_key?: string; model_id: string }
  ) => {
    await api.updateAgent(id, body);
    await reloadAgents();
  };

  const handleDeleteAgent = async (id: string) => {
    await api.deleteAgent(id);
    await reloadAgents();
  };

  const handleTestAgent = async (id: string) => api.testAgent(id);

  const handleDeleteSchedule = async (scheduleId: string) => {
    await api.deleteSchedule(scheduleId);
    showToast('定时计划已删除');
    reloadSchedules();
  };

  // ---------- 渲染 ----------

  return (
    <div className={`h-screen overflow-hidden ${theme === 'dark' ? 'dark bg-[#0A0D14] text-slate-100' : 'bg-[#ECEEF2] text-slate-900'} ${fullPage ? '' : 'flex items-center justify-center p-2 sm:p-4 lg:p-6'} font-sans transition-colors duration-200`}>
      {/* Toast Banner */}
      {toast && (
        <div className="fixed bottom-6 right-6 z-50 anim-toast">
          <div
            className={`px-4 py-3 rounded-2xl shadow-xl border flex items-center gap-2.5 text-xs font-semibold ${
              toast.type === 'error' ? 'anim-shake ' : ''
            }${
              toast.type === 'success'
                ? 'bg-emerald-950 text-white border-emerald-800'
                : toast.type === 'error'
                ? 'bg-rose-950 text-white border-rose-800'
                : 'bg-slate-900 text-white border-slate-800'
            }`}
          >
            {toast.type === 'success' ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            ) : toast.type === 'error' ? (
              <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
            ) : (
              <Info className="w-4 h-4 text-sky-400 shrink-0" />
            )}
            <span>{toast.message}</span>
          </div>
        </div>
      )}

      {/* Main Window Container */}
      <div
        className={`w-full bg-white dark:bg-[#111622] overflow-hidden flex flex-row ${
          fullPage
            ? 'h-screen'
            : 'max-w-[1560px] rounded-[32px] sm:rounded-[36px] border border-slate-200/90 dark:border-slate-800 shadow-2xl shadow-slate-300/60 dark:shadow-black/70 h-[880px] max-h-[96vh]'
        }`}
      >
        {/* Left Vertical Dark Sidebar */}
        <Sidebar
          activeTab={activeTab}
          onTabChange={(tab) => {
            setActiveTab(tab);
            if (tab !== 'accounts') {
              setSelectedAccount(null);
            }
          }}
          accountsCount={accounts.length}
          totalItemsCount={scrapedItems.length}
          theme={theme}
          onToggleTheme={toggleTheme}
          avatarUrl={avatarUrl}
        />

        {/* Right Main Container */}
        <div className="flex-1 flex flex-col min-w-0 bg-[#F8FAFC] dark:bg-[#0D1117]">
          <Header
            activeTab={activeTab}
            searchQuery={searchQuery}
            onSearchChange={setSearchQuery}
            onOpenCreateAccount={() => setIsCreateModalOpen(true)}
            runningFetch={runningFetch}
            onTabChange={setActiveTab}
          />

          <main className="flex-1 overflow-y-auto">
            <AnimatePresence mode="wait" initial={false}>
              <motion.div
                key={activeTab}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8, transition: { duration: 0.2, ease: VIEW_EASE_OUT } }}
                transition={{ duration: 0.4, ease: VIEW_EASE_IN }}
              >
            {/* View 1: 仪表盘 */}
            {activeTab === 'dashboard' && (
              <DashboardView
                accounts={accounts}
                scrapedItems={scrapedItems}
                schedules={schedules}
                stats={stats}
                onSelectAccount={(acc) => {
                  setSelectedAccount(acc);
                  setActiveTab('accounts');
                }}
                onOpenCreateAccount={() => setIsCreateModalOpen(true)}
                onViewAllData={(date) => navigate(date ? `/data?date=${date}&date_end=${date}` : '/data')}
                onOpenScheduleTab={() => setActiveTab('schedule')}
                onQuickSyncAccount={openAccountDetail}
                onLoginAccount={(acc) => setLoginModalAccount(acc)}
                onTriggerSchedule={handleTriggerSchedule}
              />
            )}

            {/* View 2: 账号管理 */}
            {activeTab === 'accounts' && (
              <div className="p-4 sm:p-6 lg:p-8">
                {selectedAccount ? (
                  <AccountDetail
                    account={selectedAccount}
                    onBack={closeAccountDetail}
                    onOpenCookiesModal={(acc) => setCookiesModalAccount(acc)}
                    onCheckHealth={handleQuickCheckHealth}
                    onToggleStatus={handleToggleStatus}
                    onToggleBrowser={handleToggleBrowser}
                    onDeleteAccount={handleDeleteAccount}
                    onFavoritesCleared={(acc) => {
                      reloadAccounts();
                      showToast(`已清空「${acc.name}」的本地收藏`);
                    }}
                    onFoldersChanged={() => {
                      void reloadAccounts();
                    }}
                    recentTasks={tasks.filter((t) => t.accountId === selectedAccount.id)}
                    allScrapedItems={scrapedItems.filter((i) => i.accountId === selectedAccount.id)}
                    onTriggerScrape={handleTriggerScrape}
                    isScrapingInProgress={scrapingAccountIds.has(selectedAccount.id)}
                    streamingItems={streamingByAccount[selectedAccount.id] || []}
                  />
                ) : (
                  <AccountsList
                    accounts={accounts}
                    onSelectAccount={openAccountDetail}
                    onOpenCreateModal={() => setIsCreateModalOpen(true)}
                    onOpenLoginModal={(acc) => setLoginModalAccount(acc)}
                    onQuickCheckHealth={handleQuickCheckHealth}
                    onRefreshProfiles={handleRefreshProfiles}
                    onRefreshProfile={handleRefreshProfile}
                  />
                )}
              </div>
            )}

            {/* View 3: 收藏数据 */}
            {activeTab === 'data' && (
              <div className="p-4 sm:p-6 lg:p-8">
                <DataBrowserView
                  accounts={accounts}
                  externalSearchQuery={searchQuery}
                  tagStats={tagStats}
                  tagGroups={tagGroups}
                  agents={agents}
                  onTaggingDone={() => {
                    const map = accountNameById();
                    reloadFavorites(map);
                    reloadTags();
                    reloadTasks(map);
                  }}
                />
              </div>
            )}

            {/* View 4: 同步任务 */}
            {activeTab === 'tasks' && (
              <div className="p-4 sm:p-6 lg:p-8">
                <TasksView
                  tasks={tasks}
                  onManualRefresh={() => {
                    reloadAccounts().then((map) => reloadTasks(map));
                    showToast('已从私有抓取服务同步最新任务执行状态');
                  }}
                />
              </div>
            )}

            {/* View 5: 日程调度 */}
            {activeTab === 'schedule' && (
              <ScheduleView
                schedules={schedules}
                accounts={accounts}
                agents={agents}
                onTriggerNow={handleTriggerSchedule}
                onToggleSchedule={handleToggleSchedule}
                onCreateSchedule={handleCreateSchedule}
                onCreateAgent={handleCreateAgent}
                onDeleteSchedule={handleDeleteSchedule}
              />
            )}

            {/* View 6: 下载队列 */}
            {activeTab === 'downloads' && <DownloadsView />}

            {/* View 7: 系统设置 */}
            {activeTab === 'settings' && (
              <SettingsView
                onShowToast={showToast}
                totalItemsCount={scrapedItems.length}
                theme={theme}
                onToggleTheme={toggleTheme}
                onSetTheme={setTheme}
                fullPage={fullPage}
                onSetFullPage={setFullPageAndSave}
                avatarUrl={avatarUrl}
                onAvatarChange={setAvatarUrl}
                agents={agents}
                onCreateAgent={handleCreateAgent}
                onUpdateAgent={handleUpdateAgent}
                onDeleteAgent={handleDeleteAgent}
                onTestAgent={handleTestAgent}
              />
            )}
              </motion.div>
            </AnimatePresence>
          </main>
        </div>
      </div>

      {/* Global Modals */}
      {isCreateModalOpen && (
        <CreateAccountModal
          onClose={() => setIsCreateModalOpen(false)}
          onCreate={handleCreateAccount}
        />
      )}

      {loginModalAccount && (
        <QRCodeLoginModal
          account={loginModalAccount}
          onClose={() => setLoginModalAccount(null)}
          onLoginDone={handleLoginDone}
        />
      )}

      {cookiesModalAccount && (
        <CookiesModal
          account={cookiesModalAccount}
          onClose={() => setCookiesModalAccount(null)}
        />
      )}

      {/* Dev 元素定位器（仅开发模式渲染） */}
      <DevInspector />
    </div>
  );
}

export default App;
