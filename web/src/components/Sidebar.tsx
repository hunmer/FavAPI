import React from 'react';
import { NavTab } from '../types';
import { 
  LayoutDashboard, 
  Smartphone, 
  Bookmark, 
  Activity, 
  CalendarDays, 
  Settings,
  Sparkles
} from 'lucide-react';

interface SidebarProps {
  activeTab: NavTab;
  onTabChange: (tab: NavTab) => void;
  accountsCount?: number;
  totalItemsCount?: number;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  onTabChange,
}) => {
  const navItems: { id: NavTab; label: string; icon: React.ElementType }[] = [
    { id: 'dashboard', label: '总览看板', icon: LayoutDashboard },
    { id: 'accounts', label: '账号管理', icon: Smartphone },
    { id: 'data', label: '收藏数据', icon: Bookmark },
    { id: 'tasks', label: '同步任务', icon: Activity },
    { id: 'schedule', label: '日程调度', icon: CalendarDays },
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
                {/* Active side indicator bar */}
                {isActive && (
                  <div className="absolute -left-3 w-1.5 h-6 bg-sky-500 rounded-r-full shadow-sm shadow-sky-500/50" />
                )}

                <button
                  type="button"
                  onClick={() => onTabChange(item.id)}
                  aria-label={item.label}
                  title={item.label}
                  className={`w-12 h-12 rounded-full flex items-center justify-center transition-all duration-200 cursor-pointer ${
                    isActive
                      ? 'bg-white text-slate-900 shadow-md shadow-black/20 scale-105 ring-2 ring-white/20'
                      : 'bg-slate-800/40 text-slate-400 hover:text-white hover:bg-slate-800/80 hover:scale-105'
                  }`}
                >
                  <Icon className="w-5 h-5 shrink-0" />
                </button>
              </div>
            );
          })}
        </nav>
      </div>

      {/* Bottom User Avatar */}
      <div className="flex flex-col items-center pt-5 border-t border-slate-800/80 w-full">
        <div 
          className="relative cursor-pointer group"
          title="本地管理员: Josh / FavAdmin"
          onClick={() => onTabChange('settings')}
        >
          <img
            src="https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&auto=format&fit=crop&q=80"
            alt="Admin"
            className="w-10 h-10 rounded-full object-cover ring-2 ring-slate-700 group-hover:ring-sky-500 transition-all duration-200"
          />
          <span className="absolute bottom-0 right-0 w-2.5 h-2.5 rounded-full bg-emerald-500 ring-2 ring-[#14161C]" />
        </div>
      </div>
    </aside>
  );
};

