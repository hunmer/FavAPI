import React from 'react';
import { ScheduledSync } from '../../types';
import { PLATFORMS } from '../../data/platforms';
import { Play, Plus, Clock, ArrowRight } from 'lucide-react';

interface ScheduleQueueCardProps {
  schedules: ScheduledSync[];
  onTriggerNow: (schedule: ScheduledSync) => void;
  onOpenScheduleTab: () => void;
}

export const ScheduleQueueCard: React.FC<ScheduleQueueCardProps> = ({
  schedules,
  onTriggerNow,
  onOpenScheduleTab,
}) => {
  return (
    <div className="bg-white dark:bg-[#161B26] rounded-3xl p-5 border border-slate-100 dark:border-slate-800 shadow-sm flex flex-col justify-between">
      <div>
        {/* Header */}
        <div className="flex items-center justify-between mb-3.5">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-xl bg-amber-50 dark:bg-amber-950/60 text-amber-600 dark:text-amber-400 flex items-center justify-center">
              <Clock className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-900 dark:text-white">定时抓取队列</h3>
              <p className="text-[11px] text-slate-400">自动化 Cron 守护调度</p>
            </div>
          </div>

          <button
            onClick={onOpenScheduleTab}
            className="text-xs text-sky-600 dark:text-sky-400 hover:text-sky-700 font-semibold flex items-center gap-1 hover:underline"
          >
            全部计划
            <ArrowRight className="w-3 h-3" />
          </button>
        </div>

        {/* Schedule List */}
        <div className="flex flex-col gap-2.5 mt-2">
          {schedules.slice(0, 3).map((item) => {
            const platform = PLATFORMS.find((p) => p.id === item.platform) || PLATFORMS[0];
            return (
              <div
                key={item.id}
                className="p-3.5 rounded-2xl bg-slate-50/80 dark:bg-slate-800/50 hover:bg-slate-50 dark:hover:bg-slate-800 border border-slate-100 dark:border-slate-800 transition-all flex items-center justify-between gap-3 group"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div
                    className="w-9 h-9 rounded-xl flex items-center justify-center text-xs font-bold shrink-0 shadow-sm"
                    style={{ backgroundColor: `${platform.color}15`, color: platform.color }}
                  >
                    {platform.name.slice(0, 2)}
                  </div>
                  <div className="min-w-0">
                    <h5 className="text-xs font-bold text-slate-900 dark:text-white truncate leading-snug">
                      {item.title}
                    </h5>
                    <div className="flex items-center gap-2 text-[11px] text-slate-400 mt-0.5">
                      <span className="font-mono text-slate-500 dark:text-slate-400">{item.cronExpr}</span>
                      <span>•</span>
                      <span className="text-sky-600 dark:text-sky-400 font-medium">{item.nextRunTime}</span>
                    </div>
                  </div>
                </div>

                <button
                  onClick={() => onTriggerNow(item)}
                  className="p-2 rounded-xl bg-white dark:bg-slate-700 hover:bg-slate-900 dark:hover:bg-slate-100 text-slate-600 dark:text-slate-200 hover:text-white dark:hover:text-slate-900 border border-slate-200 dark:border-slate-600 hover:border-slate-900 shadow-sm transition-all shrink-0 cursor-pointer"
                  title="立即触发执行此计划"
                >
                  <Play className="w-3.5 h-3.5 fill-current" />
                </button>
              </div>
            );
          })}
        </div>
      </div>

      {/* Footer / Add Quick Schedule */}
      <div className="mt-4 pt-3 border-t border-slate-50 dark:border-slate-800/80">
        <button
          onClick={onOpenScheduleTab}
          className="w-full py-2.5 rounded-xl border border-dashed border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:border-slate-300 dark:hover:border-slate-500 text-xs font-semibold flex items-center justify-center gap-1.5 transition-all cursor-pointer"
        >
          <Plus className="w-3.5 h-3.5 text-slate-400" />
          配置更多 Cron 定时规则
        </button>
      </div>
    </div>
  );
};
