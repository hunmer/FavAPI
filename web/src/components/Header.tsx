import React, { useCallback, useEffect, useState } from 'react';
import { Bell, Plus, Loader2 } from 'lucide-react';
import { NavTab } from '../types';
import { listNotifications, markNotificationsRead, NotificationRow } from '../api';
import { Popover } from './Popover';

export interface RunningFetchInfo {
  count: number;          // 正在运行的账号数
  accountNames: string[]; // 账号名列表（悬浮提示用）
  liveCount: number;      // 本次实时流已抓取条数
}

const REFRESH_INTERVAL_MS = 30_000; // 未读/列表轮询间隔

/** ISO 时间 → 相对时间文案（"x 分钟前"） */
const formatTimeAgo = (iso?: string | null) => {
  if (!iso) return '';
  const mins = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (Number.isNaN(mins)) return '';
  if (mins < 1) return '刚刚';
  if (mins < 60) return `${mins} 分钟前`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} 小时前`;
  return `${Math.floor(hours / 24)} 天前`;
};

const TYPE_DOT: Record<string, string> = {
  success: 'bg-emerald-500',
  error: 'bg-rose-500',
  info: 'bg-sky-500',
};

interface HeaderProps {
  activeTab: NavTab;
  onOpenCreateAccount: () => void;
  runningFetch?: RunningFetchInfo | null;
  /** 页面专属操作区（注入右侧控制区；如特别关注页的一键更新按钮），不传则不渲染 */
  actions?: React.ReactNode;
}

export const Header: React.FC<HeaderProps> = ({
  activeTab,
  onOpenCreateAccount,
  runningFetch,
  actions,
}) => {
  const [showNotifications, setShowNotifications] = useState(false);
  const [notifications, setNotifications] = useState<NotificationRow[]>([]);
  const [unread, setUnread] = useState(0);

  const refreshNotifications = useCallback(async () => {
    try {
      const res = await listNotifications();
      setNotifications(res.notifications);
      setUnread(res.unread);
    } catch {
      // 后端未就绪时静默，等下一轮轮询
    }
  }, []);

  useEffect(() => {
    refreshNotifications();
    const timer = setInterval(refreshNotifications, REFRESH_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [refreshNotifications]);

  const markAllRead = async () => {
    if (unread === 0) return;
    try {
      await markNotificationsRead();
      setUnread(0);
      setNotifications((prev) => prev.map((n) => ({ ...n, read: 1 })));
    } catch {
      // 失败保留未读状态，下一轮轮询自动对齐
    }
  };

  const getPageTitle = (tab: NavTab) => {
    switch (tab) {
      case 'dashboard':
        return { title: '综合仪表盘', subtitle: '全平台数据状态、活跃账号与近期抓取' };
      case 'accounts':
        return { title: '账号与会话管理', subtitle: '隔离 Profile、扫码登录与专属抓取配置' };
      case 'data':
        return { title: '收藏数据中心', subtitle: '多维度检索、标签分类与原站内容直达' };
      case 'follows':
        return { title: '特别关注博主', subtitle: '关注列表拉取、分组管理与博主最新作品追踪' };
      case 'tasks':
        return { title: '任务执行历史', subtitle: '增量抓取、全量同步与日志监控' };
      case 'schedule':
        return { title: '定时同步计划', subtitle: 'Cron 调度规则与自动化同步日历' };
      case 'downloads':
        return { title: '收藏下载队列', subtitle: 'yt-dlp / videodl 内容下载任务与进度' };
      case 'settings':
        return { title: '系统运行配置', subtitle: 'Chromium 路径、反风控间隔与数据导出' };
    }
  };

  const currentMeta = getPageTitle(activeTab);

  const notificationPanel = (
    <div className="w-80 bg-white dark:bg-[#161B26] rounded-2xl shadow-xl border border-slate-200 dark:border-slate-800 p-3">
      <div className="flex items-center justify-between pb-2 border-b border-slate-100 dark:border-slate-800 px-1">
        <span className="text-xs font-bold text-slate-900 dark:text-white">同步通知</span>
        <span
          onClick={markAllRead}
          className={`text-[10px] font-medium ${unread > 0
            ? 'text-sky-600 dark:text-sky-400 cursor-pointer hover:underline'
            : 'text-slate-400 dark:text-slate-500 cursor-default'}`}
        >
          全部已读
        </span>
      </div>
      <div className="flex flex-col gap-2 mt-2 max-h-80 overflow-y-auto">
        {notifications.length === 0 && (
          <div className="py-6 text-center text-xs text-slate-400 dark:text-slate-500">暂无通知</div>
        )}
        {notifications.map((n) => (
          <div
            key={n.notification_id}
            className="p-2 rounded-xl bg-slate-50 dark:bg-slate-800/60 hover:bg-slate-100/80 dark:hover:bg-slate-800 transition-colors flex flex-col gap-0.5"
          >
            <span className="text-xs font-medium text-slate-800 dark:text-slate-200 leading-snug flex items-center gap-1.5">
              <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${TYPE_DOT[n.type] || TYPE_DOT.info}`} />
              {n.title}
            </span>
            {n.detail && (
              <span className="text-[10px] text-slate-400 dark:text-slate-500 truncate" title={n.detail}>
                {n.detail}
              </span>
            )}
            <span className="text-[10px] text-slate-400 dark:text-slate-500">{formatTimeAgo(n.created_at)}</span>
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <header className="h-20 px-6 lg:px-8 border-b border-slate-100 dark:border-slate-800/80 bg-white/85 dark:bg-[#12151E]/85 backdrop-blur-md grid grid-cols-[minmax(0,1fr)_auto] md:grid-cols-[16rem_minmax(0,1fr)] items-center gap-4 shrink-0 z-20 transition-colors duration-200">
      {/* Left: View Title & Subtitle */}
      <div className="flex flex-col min-w-0">
        <h1 className="text-xl font-bold text-slate-900 dark:text-white tracking-tight flex items-center gap-2">
          {currentMeta.title}
          {activeTab === 'dashboard' && (
            <span className="hidden sm:inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full bg-emerald-50 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              就绪
            </span>
          )}
        </h1>
        <p className="text-xs text-slate-500 dark:text-slate-400 truncate hidden sm:block">
          {currentMeta.subtitle}
        </p>
      </div>

      {/* Right Controls: Auto-refresh, Page Actions, Add Account, Notification, Avatar */}
      <div className="flex items-center gap-2 sm:gap-2.5 shrink-0 justify-self-end">
        {/* 页面专属操作（如特别关注页的一键更新），每个页面各自注入 */}
        {actions}

        {/* 抓取进度指示：仅有任务运行时展示 */}
        {runningFetch && runningFetch.count > 0 && (
          <div
            className="flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-full text-xs font-semibold border transition-all bg-emerald-50 dark:bg-emerald-950/50 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800"
            title={`正在运行：${runningFetch.accountNames.join('、') || '定时任务'}`}
          >
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            <span className="hidden sm:inline whitespace-nowrap">
              {runningFetch.count} 个账号抓取中
              {runningFetch.liveCount > 0 ? ` · 已入库 ${runningFetch.liveCount} 条` : ''}
            </span>
          </div>
        )}

        {/* Quick Add Account Button */}
        <button
          onClick={onOpenCreateAccount}
          className="flex items-center gap-1.5 px-3 sm:px-3.5 py-1.5 rounded-full text-xs font-semibold bg-slate-900 dark:bg-white text-white dark:text-slate-900 hover:bg-slate-800 dark:hover:bg-slate-100 active:scale-95 transition-all shadow-sm shadow-slate-900/20 dark:shadow-black/40"
        >
          <Plus className="w-3.5 h-3.5 text-white dark:text-slate-900" />
          <span className="hidden sm:inline">新建账号</span>
        </button>

        {/* Notifications Dropdown */}
        <Popover
          open={showNotifications}
          onClose={() => setShowNotifications(false)}
          content={notificationPanel}
        >
          <button
            onClick={() => setShowNotifications(!showNotifications)}
            className="relative p-2 rounded-full text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            title="通知中心"
          >
            <Bell className="w-4 h-4" />
            {unread > 0 && (
              <span className="absolute top-0.5 right-0.5 min-w-[16px] h-4 px-1 rounded-full bg-sky-500 ring-2 ring-white dark:ring-[#12151E] text-[10px] font-bold text-white flex items-center justify-center">
                {unread > 99 ? '99+' : unread}
              </span>
            )}
          </button>
        </Popover>
      </div>
    </header>
  );
};
