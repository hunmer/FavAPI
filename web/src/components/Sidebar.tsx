import React from 'react';
import { motion } from 'motion/react';
import { NavTab } from '../types';
import {
  LayoutDashboard,
  Smartphone,
  Bookmark,
  Activity,
  CalendarDays,
  Download,
  Settings,
  Sparkles,
  Sun,
  Moon,
  User
} from 'lucide-react';

// tab 切换移动效果（motion-design Corporate）：屏内过渡统一 Snappy 曲线
const EASE_SNAPPY: [number, number, number, number] = [0.2, 0, 0, 1];

interface SidebarProps {
  activeTab: NavTab;
  onTabChange: (tab: NavTab) => void;
  accountsCount?: number;
  totalItemsCount?: number;
  /** 下载队列进行中条数（pending+running），>0 时在下载图标上显示 badge */
  downloadsActive?: number;
  theme: 'light' | 'dark';
  onToggleTheme: () => void;
  avatarUrl?: string | null;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  onTabChange,
  downloadsActive = 0,
  theme,
  onToggleTheme,
  avatarUrl,
}) => {
  const navItems: { id: NavTab; label: string; icon: React.ElementType }[] = [
    { id: 'dashboard', label: '总览看板', icon: LayoutDashboard },
    { id: 'accounts', label: '账号管理', icon: Smartphone },
    { id: 'data', label: '收藏数据', icon: Bookmark },
    { id: 'tasks', label: '同步任务', icon: Activity },
    { id: 'schedule', label: '日程调度', icon: CalendarDays },
    { id: 'downloads', label: '下载队列', icon: Download },
    { id: 'settings', label: '系统设置', icon: Settings },
  ];

  return (
    <aside className="w-[76px] bg-[#14161C] text-slate-300 flex flex-col justify-between items-center py-6 px-3 shrink-0 border-r border-slate-800/80 transition-all select-none">
      {/* Top Brand Logo & Navigation */}
      <div className="flex flex-col items-center gap-7 w-full">
        {/* Brand Logo (Circular Icon) */}
        <div 
          onClick={() => onTabChange('dashboard')}
          className="w-12 h-12 rounded-full bg-gradient-to-tr from-sky-500 via-indigo-600 to-purple-500 flex items-center justify-center shadow-lg shadow-sky-500/25 cursor-pointer hover:scale-105 active:scale-95 transition-all duration-200 group"
          title="FavAPI Web Console — 点击返回总览"
        >
          <Sparkles className="w-5 h-5 text-white group-hover:rotate-12 transition-transform duration-300" />
        </div>

        {/* Navigation Items (Circular Icon Buttons) */}
        <nav className="flex flex-col items-center gap-3.5 w-full">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <div key={item.id} className="relative flex items-center justify-center w-full">
                {/* Active side indicator bar：layoutId 让指示条随 tab 切换平滑滑动 */}
                {isActive && (
                  <motion.div
                    layoutId="sidebar-indicator"
                    className="absolute -left-3 w-1.5 h-6 bg-sky-500 rounded-r-full shadow-sm shadow-sky-500/50"
                    transition={{ duration: 0.25, ease: EASE_SNAPPY }}
                  />
                )}

                <button
                  type="button"
                  onClick={() => onTabChange(item.id)}
                  aria-label={item.label}
                  title={item.label}
                  className={`relative w-12 h-12 rounded-full flex items-center justify-center transition-all duration-200 cursor-pointer ${
                    isActive
                      ? 'text-slate-900 scale-105'
                      : 'bg-slate-800/40 text-slate-400 hover:text-white hover:bg-slate-800/80 hover:scale-105'
                  }`}
                >
                  {/* 激活高亮胶囊：从上一个 tab 滑移过来 */}
                  {isActive && (
                    <motion.span
                      layoutId="sidebar-pill"
                      className="absolute inset-0 rounded-full bg-white shadow-md shadow-black/20 ring-2 ring-white/20"
                      transition={{ duration: 0.3, ease: EASE_SNAPPY }}
                    />
                  )}
                  <Icon className="relative z-10 w-5 h-5 shrink-0" />
                  {/* 下载队列进行中数量 badge */}
                  {item.id === 'downloads' && downloadsActive > 0 && (
                    <span className="absolute -top-0.5 -right-0.5 z-20 min-w-[18px] h-[18px] px-1 rounded-full bg-sky-500 text-white text-[10px] font-bold flex items-center justify-center ring-2 ring-[#14161C]">
                      {downloadsActive > 99 ? '99+' : downloadsActive}
                    </span>
                  )}
                </button>
              </div>
            );
          })}
        </nav>
      </div>

      {/* Bottom: Theme Toggle & User Avatar */}
      <div className="flex flex-col items-center gap-3.5 pt-5 border-t border-slate-800/80 w-full">
        {/* Dark/Light Mode Toggle Button */}
        <button
          onClick={onToggleTheme}
          className="w-12 h-12 rounded-full flex items-center justify-center bg-slate-800/40 text-slate-400 hover:text-white hover:bg-slate-800/80 hover:scale-105 active:scale-95 transition-all duration-200 cursor-pointer"
          title={theme === 'dark' ? '当前：暗色模式，点击切换为亮色模式' : '当前：亮色模式，点击切换为暗色模式'}
          aria-label="暗色/亮色切换"
        >
          {theme === 'dark' ? (
            <Sun className="w-5 h-5 text-amber-400 fill-amber-400/20" />
          ) : (
            <Moon className="w-5 h-5 text-indigo-600 fill-indigo-600/20" />
          )}
        </button>

        {/* User Avatar */}
        <div 
          className="relative cursor-pointer group"
          title="本地管理员: Josh / FavAdmin"
          onClick={() => onTabChange('settings')}
        >
          {avatarUrl ? (
            <img
              src={avatarUrl}
              alt="Admin"
              className="w-10 h-10 rounded-full object-cover ring-2 ring-slate-700 group-hover:ring-sky-500 transition-all duration-200"
            />
          ) : (
            <div className="w-10 h-10 rounded-full bg-slate-800/60 flex items-center justify-center ring-2 ring-slate-700 group-hover:ring-sky-500 transition-all duration-200">
              <User className="w-5 h-5 text-slate-400" />
            </div>
          )}
          <span className="absolute bottom-0 right-0 w-2.5 h-2.5 rounded-full bg-emerald-500 ring-2 ring-[#14161C]" />
        </div>
      </div>
    </aside>
  );
};

