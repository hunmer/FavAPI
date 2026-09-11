import React from 'react';
import { Account, ScrapedItem, ScheduledSync } from '../../types';
import * as api from '../../api';
import { StatCard } from './StatCard';
import { ActiveAccountCard } from './ActiveAccountCard';
import { CalendarCard } from './CalendarCard';
import { ScheduleQueueCard } from './ScheduleQueueCard';
import {
  Users,
  Bookmark,
  HardDrive,
  Plus
} from 'lucide-react';

function fmtSize(bytes?: number): string {
  if (!bytes) return '—';
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(0)} MB`;
  return `${(bytes / 1024).toFixed(0)} KB`;
}

interface DashboardViewProps {
  accounts: Account[];
  scrapedItems: ScrapedItem[];
  schedules: ScheduledSync[];
  stats?: api.StatsData | null;
  onSelectAccount: (account: Account) => void;
  onOpenCreateAccount: () => void;
  onViewAllData: (date?: string) => void;
  onOpenScheduleTab: () => void;
  onQuickSyncAccount: (account: Account) => void;
  onLoginAccount: (account: Account) => void;
  onTriggerSchedule: (schedule: ScheduledSync) => void;
}

export const DashboardView: React.FC<DashboardViewProps> = ({
  accounts,
  scrapedItems,
  schedules,
  stats,
  onSelectAccount,
  onOpenCreateAccount,
  onViewAllData,
  onOpenScheduleTab,
  onQuickSyncAccount,
  onLoginAccount,
  onTriggerSchedule,
}) => {

  return (
    <div className="flex flex-col lg:flex-row gap-6 p-4 sm:p-6 lg:p-8">
      {/* Left Column (Calendar with daily ingested collections list + Schedule Queue) */}
      <div className="w-full lg:w-[380px] xl:w-[420px] shrink-0 flex flex-col gap-6">
        {/* Calendar Card with integrated daily collections list */}
        <div className="anim-card-enter">
          <CalendarCard
            scrapedItems={scrapedItems}
            onViewAllData={onViewAllData}
          />
        </div>

        {/* Schedule Queue Card */}
        <div className="anim-card-enter" style={{ animationDelay: '80ms' }}>
          <ScheduleQueueCard
            schedules={schedules}
            onTriggerNow={onTriggerSchedule}
            onOpenScheduleTab={onOpenScheduleTab}
          />
        </div>
      </div>

      {/* Right / Main Overview Column */}
      <div className="flex-1 flex flex-col gap-6 min-w-0">
        {/* Top 3 Stat Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="anim-card-enter">
            <StatCard
              title="已纳管账号"
              value={`${stats?.accounts_active ?? accounts.filter((a) => a.status === 'active').length} / ${stats?.accounts_total ?? accounts.length}`}
              subtitle={stats?.schedules_active ? `${stats.schedules_active} 个定时任务运行中` : '隔离 Profile 均正常映射'}
              icon={Users}
              iconColor="text-sky-600"
              iconBg="bg-sky-50"
              trend={{ text: stats?.tasks_running ? `${stats.tasks_running} 个任务执行中` : '全平台就绪', isPositive: true }}
            />
          </div>
          <div className="anim-card-enter" style={{ animationDelay: '60ms' }}>
            <StatCard
              title="累计入库收藏"
              value={stats?.favorites_total ?? scrapedItems.length}
              subtitle={`今日新增 ${stats?.today_new_favorites ?? 0} 条`}
              icon={Bookmark}
              iconColor="text-indigo-600"
              iconBg="bg-indigo-50"
            />
          </div>
          <div className="anim-card-enter" style={{ animationDelay: '120ms' }}>
            <StatCard
              title="本地存储占用"
              value={fmtSize(stats?.data_dir_size_bytes)}
              subtitle={stats ? `SQLite ${fmtSize(stats.db_size_bytes)} · 内容元数据 ${stats.contents_total} 条` : 'SQLite + 浏览器 Profile'}
              icon={HardDrive}
              iconColor="text-purple-600"
              iconBg="bg-purple-50"
            />
          </div>
        </div>

        {/* Section: 活跃账号与抓取状态 */}
        <div className="flex flex-col gap-3.5">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-base font-bold text-slate-900 dark:text-white">活跃账号与隔离工作台</h3>
              <p className="text-xs text-slate-400 dark:text-slate-400">点击账号进入专属会话、Cookies 及增量抓取设置</p>
            </div>
            <button
              type="button"
              onClick={onOpenCreateAccount}
              className="text-xs font-semibold text-sky-600 dark:text-sky-400 hover:text-sky-700 dark:hover:text-sky-300 flex items-center gap-1 hover:underline cursor-pointer"
            >
              <Plus className="w-3.5 h-3.5" />
              接入新平台账号
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {accounts.map((account, idx) => (
              <div key={account.id} className="anim-card-enter" style={{ animationDelay: `${Math.min(idx * 40, 240)}ms` }}>
                <ActiveAccountCard
                  account={account}
                  onSelect={onSelectAccount}
                  onQuickSync={onQuickSyncAccount}
                  onLogin={onLoginAccount}
                />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
