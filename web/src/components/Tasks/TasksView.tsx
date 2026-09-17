import React, { useState } from 'react';
import { TaskRecord, PlatformId } from '../../types';
import { PLATFORMS } from '../../data/platforms';
import {
  ListTodo,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  Filter,
  Search,
  ChevronRight,
  X,
  FileCode,
  Terminal,
  Trash2,
} from 'lucide-react';

interface TasksViewProps {
  tasks: TaskRecord[];
  onManualRefresh: () => void;
  onClearRecords: () => void | Promise<void>;
}

export const TasksView: React.FC<TasksViewProps> = ({
  tasks,
  onManualRefresh,
  onClearRecords,
}) => {
  const [platformFilter, setPlatformFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedTaskDetail, setSelectedTaskDetail] = useState<TaskRecord | null>(null);

  const filteredTasks = tasks.filter((t) => {
    const matchPlatform = platformFilter === 'all' || t.platform === platformFilter;
    const matchStatus = statusFilter === 'all' || t.status === statusFilter;
    const matchSearch =
      t.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      t.accountName.toLowerCase().includes(searchQuery.toLowerCase()) ||
      t.operationType.toLowerCase().includes(searchQuery.toLowerCase());
    return matchPlatform && matchStatus && matchSearch;
  });

  return (
    <div id="tasks-view" className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
            任务记录 (全局执行历史)
          </h2>
          <p className="text-xs sm:text-sm text-slate-500 dark:text-slate-400 mt-0.5">
            汇聚所有平台的增量抓取、全量归档及健康检查任务，支持 5 秒自动轮询无感刷新。
          </p>
        </div>

        {/* Manual refresh actions */}
        <div className="flex items-center gap-2.5">
          <button
            type="button"
            onClick={onManualRefresh}
            className="px-3 py-2 rounded-xl bg-white dark:bg-[#161B26] border border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-800 dark:text-slate-200 text-xs font-semibold shadow-2xs inline-flex items-center gap-1.5 transition-colors cursor-pointer"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            立即刷新
          </button>
          <button
            type="button"
            onClick={() => {
              if (tasks.length === 0) return;
              if (window.confirm('确定要清空全部任务记录吗？此操作不可恢复。')) {
                onClearRecords();
              }
            }}
            className="px-3 py-2 rounded-xl bg-white dark:bg-[#161B26] border border-rose-200 dark:border-rose-900/60 hover:bg-rose-50 dark:hover:bg-rose-950/40 text-rose-600 dark:text-rose-400 text-xs font-semibold shadow-2xs inline-flex items-center gap-1.5 transition-colors cursor-pointer"
          >
            <Trash2 className="w-3.5 h-3.5" />
            清空记录
          </button>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="bg-white dark:bg-[#161B26] p-3.5 rounded-2xl border border-slate-200/80 dark:border-slate-800 shadow-2xs flex flex-col md:flex-row md:items-center justify-between gap-3">
        {/* Status tabs */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 md:pb-0">
          {[
            { id: 'all', label: '全部状态' },
            { id: 'running', label: '执行中' },
            { id: 'success', label: '成功' },
            { id: 'failed', label: '失败' },
          ].map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => setStatusFilter(s.id)}
              className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors cursor-pointer ${
                statusFilter === s.id
                  ? 'bg-slate-900 dark:bg-sky-600 text-white shadow-2xs'
                  : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700'
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          {/* Platform select */}
          <select
            value={platformFilter}
            onChange={(e) => setPlatformFilter(e.target.value)}
            className="px-3 py-1.5 rounded-xl border border-slate-200 dark:border-slate-700 text-xs bg-slate-50 dark:bg-slate-800 text-slate-700 dark:text-slate-200 focus:outline-none"
          >
            <option value="all">全部平台</option>
            {PLATFORMS.filter((p) => p.isSupported).map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>

          {/* Search */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="搜索任务ID、账号..."
              className="pl-8 pr-3 py-1.5 rounded-xl border border-slate-200 dark:border-slate-700 text-xs w-48 focus:outline-none focus:ring-2 focus:ring-slate-900 dark:focus:ring-sky-500 bg-slate-50/50 dark:bg-slate-800 text-slate-800 dark:text-slate-100"
            />
          </div>
        </div>
      </div>

      {/* Tasks Table */}
      <div className="bg-white dark:bg-[#161B26] rounded-[28px] border border-slate-200/80 dark:border-slate-800 shadow-2xs overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-slate-50/80 dark:bg-slate-800/60 text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-800 font-semibold">
                <th className="py-3 px-4">任务 ID</th>
                <th className="py-3 px-4">目标平台</th>
                <th className="py-3 px-4">绑定账号</th>
                <th className="py-3 px-4">操作类型</th>
                <th className="py-3 px-4">开始时间 / 耗时</th>
                <th className="py-3 px-4 text-center">执行状态</th>
                <th className="py-3 px-4 text-right">抓取入库数</th>
                <th className="py-3 px-4 text-center">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {filteredTasks.length > 0 ? (
                filteredTasks.map((t, idx) => {
                  const platformMeta = PLATFORMS.find((p) => p.id === t.platform);
                  return (
                    <tr
                      key={t.id}
                      onClick={() => setSelectedTaskDetail(t)}
                      className="anim-row-enter hover:bg-slate-50/70 dark:hover:bg-slate-800/50 cursor-pointer transition-colors"
                      style={{ animationDelay: `${Math.min(idx * 20, 200)}ms` }}
                    >
                      <td className="py-3.5 px-4 font-mono font-bold text-slate-900 dark:text-slate-100">
                        {t.id}
                      </td>
                      <td className="py-3.5 px-4">
                        <span className={`px-2 py-0.5 rounded-full text-[11px] font-bold border ${platformMeta?.badgeBg}`}>
                          {platformMeta?.name.split(' ')[0]}
                        </span>
                      </td>
                      <td className="py-3.5 px-4 font-medium text-slate-800 dark:text-slate-200">
                        {t.accountName}
                      </td>
                      <td className="py-3.5 px-4">
                        <span className="font-semibold text-slate-700 dark:text-slate-300 bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded">
                          {t.operationType}
                        </span>
                      </td>
                      <td className="py-3.5 px-4 text-slate-500 dark:text-slate-400 whitespace-nowrap">
                        <div>{t.startTime}</div>
                        <div className="text-[10px] text-slate-400">耗时: {t.durationSec} 秒</div>
                      </td>
                      <td className="py-3.5 px-4 text-center whitespace-nowrap">
                        {t.status === 'success' ? (
                          <span className="inline-flex items-center gap-1 text-[11px] font-bold text-emerald-700 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/60 px-2.5 py-0.5 rounded-full border border-emerald-200 dark:border-emerald-800">
                            <CheckCircle2 className="w-3 h-3 text-emerald-600 dark:text-emerald-400" />
                            成功
                          </span>
                        ) : t.status === 'running' ? (
                          <span className="inline-flex items-center gap-1 text-[11px] font-bold text-indigo-700 dark:text-sky-300 bg-indigo-50 dark:bg-sky-950/60 px-2.5 py-0.5 rounded-full border border-indigo-200 dark:border-sky-800">
                            <RefreshCw className="w-3 h-3 animate-spin text-indigo-600 dark:text-sky-400" />
                            执行中
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-[11px] font-bold text-rose-700 dark:text-rose-400 bg-rose-50 dark:bg-rose-950/60 px-2.5 py-0.5 rounded-full border border-rose-200 dark:border-rose-800">
                            <AlertTriangle className="w-3 h-3 text-rose-600 dark:text-rose-400" />
                            失败
                          </span>
                        )}
                      </td>
                      <td className="py-3.5 px-4 text-right">
                        <span className="font-extrabold text-sm text-slate-900 dark:text-white">
                          +{t.newCount}
                        </span>
                        <span className="text-slate-400 text-[11px] ml-1">/ {t.scrapedCount}</span>
                      </td>
                      <td className="py-3.5 px-4 text-center">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedTaskDetail(t);
                          }}
                          className="p-1 rounded-lg hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 transition-colors"
                          title="查看任务详细日志"
                        >
                          <ChevronRight className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={8} className="py-12 text-center text-slate-400">
                    没有找到符合条件的任务记录
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Task Log Drawer Modal */}
      {selectedTaskDetail && (
        <div
          className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4 anim-backdrop-enter"
          onClick={() => setSelectedTaskDetail(null)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="anim-modal-enter bg-white dark:bg-[#161B26] w-full max-w-xl rounded-[32px] shadow-2xl border border-slate-100 dark:border-slate-800 overflow-hidden flex flex-col max-h-[85vh]"
          >
            <div className="p-5 bg-slate-50 dark:bg-slate-800/60 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
              <div>
                <h3 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
                  <Terminal className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
                  任务详情与运行日志 • {selectedTaskDetail.id}
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  {selectedTaskDetail.accountName} • {selectedTaskDetail.operationType}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setSelectedTaskDetail(null)}
                className="w-8 h-8 rounded-full bg-white dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600 text-slate-700 dark:text-slate-200 flex items-center justify-center shadow-2xs cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-6 space-y-4 overflow-y-auto">
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div className="p-3 bg-slate-50 dark:bg-slate-800/50 rounded-xl border border-slate-100 dark:border-slate-800">
                  <span className="text-slate-400">开始时间</span>
                  <div className="font-semibold text-slate-800 dark:text-slate-200 mt-0.5">{selectedTaskDetail.startTime}</div>
                </div>
                <div className="p-3 bg-slate-50 dark:bg-slate-800/50 rounded-xl border border-slate-100 dark:border-slate-800">
                  <span className="text-slate-400">执行耗时</span>
                  <div className="font-semibold text-slate-800 dark:text-slate-200 mt-0.5">{selectedTaskDetail.durationSec} 秒</div>
                </div>
                <div className="p-3 bg-slate-50 dark:bg-slate-800/50 rounded-xl border border-slate-100 dark:border-slate-800">
                  <span className="text-slate-400">抓取入库总量</span>
                  <div className="font-semibold text-slate-800 dark:text-slate-200 mt-0.5">
                    新增 {selectedTaskDetail.newCount} / 共抓取 {selectedTaskDetail.scrapedCount}
                  </div>
                </div>
                <div className="p-3 bg-slate-50 dark:bg-slate-800/50 rounded-xl border border-slate-100 dark:border-slate-800">
                  <span className="text-slate-400">Next Cursor</span>
                  <div className="font-mono text-[11px] text-slate-800 dark:text-slate-200 mt-0.5 truncate">
                    {selectedTaskDetail.cursor || '无 (已到达末尾)'}
                  </div>
                </div>
              </div>

              {selectedTaskDetail.errorMessage ? (
                <div className="p-4 bg-rose-50 dark:bg-rose-950/60 border border-rose-200 dark:border-rose-800 rounded-2xl space-y-1">
                  <div className="text-xs font-bold text-rose-800 dark:text-rose-300 flex items-center gap-1.5">
                    <AlertTriangle className="w-4 h-4 text-rose-600 dark:text-rose-400" />
                    执行异常日志
                  </div>
                  <pre className="text-xs text-rose-700 dark:text-rose-300 font-mono whitespace-pre-wrap">
                    {selectedTaskDetail.errorMessage}
                  </pre>
                </div>
              ) : (
                <div className="p-4 bg-slate-900 dark:bg-black/80 border border-slate-800 text-slate-200 rounded-2xl font-mono text-xs space-y-1">
                  <div className="text-emerald-400">
                    [FavAPI Core] Task {selectedTaskDetail.id} completed with status: SUCCESS
                  </div>
                  <div className="text-slate-400">
                    [1] Loading Chromium browser profile from ~/.favapi/profiles/...
                  </div>
                  <div className="text-slate-400">
                    [2] Authenticated cookies verified for {selectedTaskDetail.accountName}
                  </div>
                  <div className="text-slate-400">
                    [3] Streamed pagination finished. Processed {selectedTaskDetail.scrapedCount} items.
                  </div>
                  <div className="text-emerald-300">
                    [4] Successfully persisted {selectedTaskDetail.newCount} new items into SQLite/Postgres.
                  </div>
                </div>
              )}
            </div>

            <div className="p-4 bg-slate-50 dark:bg-slate-800/60 border-t border-slate-100 dark:border-slate-800 flex justify-end">
              <button
                type="button"
                onClick={() => setSelectedTaskDetail(null)}
                className="px-5 py-2 bg-slate-900 dark:bg-sky-600 text-white text-xs font-bold rounded-xl cursor-pointer"
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
