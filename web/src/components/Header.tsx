import React, { useState } from 'react';
import { Search, Bell, Plus, RefreshCw, CheckCircle2, ShieldCheck, Sparkles, X, Sun, Moon } from 'lucide-react';
import { NavTab } from '../types';

interface HeaderProps {
  activeTab: NavTab;
  searchQuery: string;
  onSearchChange: (query: string) => void;
  onOpenCreateAccount: () => void;
  autoRefreshEnabled: boolean;
  onToggleAutoRefresh: () => void;
  refreshSecondsLeft: number;
  onTabChange: (tab: NavTab) => void;
  theme: 'light' | 'dark';
  onToggleTheme: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  activeTab,
  searchQuery,
  onSearchChange,
  onOpenCreateAccount,
  autoRefreshEnabled,
  onToggleAutoRefresh,
  refreshSecondsLeft,
  onTabChange,
  theme,
  onToggleTheme,
}) => {
  const [showNotifications, setShowNotifications] = useState(false);

  const getPageTitle = (tab: NavTab) => {
    switch (tab) {
      case 'dashboard':
        return { title: '综合仪表盘', subtitle: '全平台数据状态、活跃账号与近期抓取' };
      case 'accounts':
        return { title: '账号与会话管理', subtitle: '隔离 Profile、扫码登录与专属抓取配置' };
      case 'data':
        return { title: '收藏数据中心', subtitle: '多维度检索、标签分类与原站内容直达' };
      case 'tasks':
        return { title: '任务执行历史', subtitle: '增量抓取、全量同步与日志监控' };
      case 'schedule':
        return { title: '定时同步计划', subtitle: 'Cron 调度规则与自动化同步日历' };
      case 'settings':
        return { title: '系统运行配置', subtitle: 'Chromium 路径、反风控间隔与数据导出' };
    }
  };

  const currentMeta = getPageTitle(activeTab);

  const sampleNotifications = [
    { id: 1, title: 'B站设计灵感收藏夹增量抓取成功', time: '10 分钟前', type: 'success' },
    { id: 2, title: '小红书美学账号登录态有效（已健康巡检）', time: '1 小时前', type: 'info' },
    { id: 3, title: '今日已自动入库 24 条新收藏内容', time: '3 小时前', type: 'success' },
  ];

  return (
    <header className="h-20 px-6 lg:px-8 border-b border-slate-100 dark:border-slate-800/80 bg-white/85 dark:bg-[#12151E]/85 backdrop-blur-md flex items-center justify-between gap-4 shrink-0 z-20 transition-colors duration-200">
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

      {/* Center: Global Search Bar */}
      <div className="flex-1 max-w-md mx-2 relative hidden md:block">
        <div className="relative flex items-center">
          <Search className="w-4 h-4 text-slate-400 dark:text-slate-500 absolute left-3.5 pointer-events-none" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => {
              onSearchChange(e.target.value);
              if (activeTab !== 'data' && e.target.value) {
                onTabChange('data');
              }
            }}
            placeholder="搜索全网收藏标题、作者、标签、账号..."
            className="w-full pl-10 pr-12 py-2 text-xs bg-slate-100/80 dark:bg-slate-800/80 hover:bg-slate-100 dark:hover:bg-slate-800 focus:bg-white dark:focus:bg-slate-900 text-slate-800 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500 rounded-full border border-transparent focus:border-sky-300 dark:focus:border-sky-500 focus:ring-4 focus:ring-sky-100 dark:focus:ring-sky-950/40 transition-all outline-none"
          />
          {searchQuery ? (
            <button
              onClick={() => onSearchChange('')}
              className="absolute right-3 p-0.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded-full"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          ) : (
            <span className="absolute right-3 text-[10px] text-slate-400 dark:text-slate-500 font-mono bg-slate-200/70 dark:bg-slate-700/70 px-1.5 py-0.5 rounded">
              ⌘K
            </span>
          )}
        </div>
      </div>

      {/* Right Controls: Auto-refresh, Dark/Light Mode, Add Account, Notification, Avatar */}
      <div className="flex items-center gap-2 sm:gap-2.5 shrink-0">
        {/* Dark/Light Mode Toggle Button */}
        <button
          onClick={onToggleTheme}
          className="flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-full text-xs font-semibold border transition-all duration-200 bg-slate-100 dark:bg-slate-800/90 text-slate-700 dark:text-slate-200 border-slate-200/80 dark:border-slate-700 hover:bg-slate-200 dark:hover:bg-slate-700 active:scale-95 cursor-pointer shadow-xs"
          title={theme === 'dark' ? '当前：暗色模式，点击切换为亮色模式' : '当前：亮色模式，点击切换为暗色模式'}
          aria-label="暗色/亮色切换"
        >
          {theme === 'dark' ? (
            <>
              <Sun className="w-3.5 h-3.5 text-amber-400 fill-amber-400/20" />
              <span className="hidden sm:inline text-amber-300 font-medium">暗色</span>
            </>
          ) : (
            <>
              <Moon className="w-3.5 h-3.5 text-indigo-600 fill-indigo-600/20" />
              <span className="hidden sm:inline text-slate-700 font-medium">亮色</span>
            </>
          )}
        </button>

        {/* 5s Auto-refresh Switch */}
        <button
          onClick={onToggleAutoRefresh}
          className={`flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-full text-xs font-semibold border transition-all ${
            autoRefreshEnabled
              ? 'bg-sky-50 dark:bg-sky-950/50 text-sky-700 dark:text-sky-300 border-sky-200 dark:border-sky-800 hover:bg-sky-100 dark:hover:bg-sky-900/50'
              : 'bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 border-slate-200 dark:border-slate-700 hover:bg-slate-200 dark:hover:bg-slate-700'
          }`}
          title={autoRefreshEnabled ? '点击暂停后台自动轮询' : '点击开启 5s 自动轮询'}
        >
          <RefreshCw className={`w-3.5 h-3.5 ${autoRefreshEnabled ? 'animate-spin text-sky-600 dark:text-sky-400' : ''}`} style={{ animationDuration: '3s' }} />
          <span className="hidden sm:inline">
            {autoRefreshEnabled ? `轮询中 (${refreshSecondsLeft}s)` : '已暂停'}
          </span>
        </button>

        {/* Quick Add Account Button */}
        <button
          onClick={onOpenCreateAccount}
          className="flex items-center gap-1.5 px-3 sm:px-3.5 py-1.5 rounded-full text-xs font-semibold bg-slate-900 dark:bg-white text-white dark:text-slate-900 hover:bg-slate-800 dark:hover:bg-slate-100 active:scale-95 transition-all shadow-sm shadow-slate-900/20 dark:shadow-black/40"
        >
          <Plus className="w-3.5 h-3.5 text-white dark:text-slate-900" />
          <span className="hidden sm:inline">新建账号</span>
        </button>

        {/* Notifications Dropdown */}
        <div className="relative">
          <button
            onClick={() => setShowNotifications(!showNotifications)}
            className="relative p-2 rounded-full text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            title="通知中心"
          >
            <Bell className="w-4 h-4" />
            <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-sky-500 ring-2 ring-white dark:ring-[#12151E]" />
          </button>

          {showNotifications && (
            <div className="absolute right-0 mt-2 w-80 bg-white dark:bg-[#161B26] rounded-2xl shadow-xl border border-slate-200 dark:border-slate-800 p-3 z-50 animate-in fade-in zoom-in-95 duration-150">
              <div className="flex items-center justify-between pb-2 border-b border-slate-100 dark:border-slate-800 px-1">
                <span className="text-xs font-bold text-slate-900 dark:text-white">同步通知</span>
                <span className="text-[10px] text-sky-600 dark:text-sky-400 font-medium cursor-pointer hover:underline">全部已读</span>
              </div>
              <div className="flex flex-col gap-2 mt-2">
                {sampleNotifications.map((n) => (
                  <div key={n.id} className="p-2 rounded-xl bg-slate-50 dark:bg-slate-800/60 hover:bg-slate-100/80 dark:hover:bg-slate-800 transition-colors flex flex-col gap-0.5">
                    <span className="text-xs font-medium text-slate-800 dark:text-slate-200 leading-snug">{n.title}</span>
                    <span className="text-[10px] text-slate-400 dark:text-slate-500">{n.time}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Avatar */}
        <div 
          onClick={() => onTabChange('settings')}
          className="w-8 h-8 rounded-full overflow-hidden border border-slate-200 dark:border-slate-700 cursor-pointer ring-2 ring-transparent hover:ring-sky-200 dark:hover:ring-sky-800 transition-all"
          title="系统与个人设置"
        >
          <img
            src="https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&auto=format&fit=crop&q=80"
            alt="User Avatar"
            className="w-full h-full object-cover"
          />
        </div>
      </div>
    </header>
  );
};

