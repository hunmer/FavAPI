import React from 'react';
import { TaskRecord } from '../../../types';
import { RefreshCw } from 'lucide-react';

interface TasksTabProps {
  recentTasks: TaskRecord[];
}

/** 最近任务记录列表：状态、耗时、游标保存与入库统计 */
export const TasksTab: React.FC<TasksTabProps> = ({ recentTasks }) => (
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
);
