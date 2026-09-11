import React, { useCallback, useEffect, useState } from 'react';
import * as api from '../../api';
import { DownloadRow } from '../../api';
import {
  Download,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Loader2,
  Trash2,
  RotateCcw,
  ExternalLink,
  HardDriveDownload,
  PauseCircle,
  PlayCircle,
} from 'lucide-react';

const STATUS_META: Record<DownloadRow['status'], { label: string; cls: string }> = {
  pending: { label: '排队中', cls: 'bg-slate-100 text-slate-600 border-slate-200 dark:bg-slate-800/60 dark:text-slate-300 dark:border-slate-700' },
  running: { label: '下载中', cls: 'bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-950/50 dark:text-sky-300 dark:border-sky-800' },
  success: { label: '已完成', cls: 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/50 dark:text-emerald-300 dark:border-emerald-800' },
  failed: { label: '失败', cls: 'bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/50 dark:text-rose-300 dark:border-rose-800' },
  canceled: { label: '已取消', cls: 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/50 dark:text-amber-300 dark:border-amber-800' },
  paused: { label: '已暂停', cls: 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/50 dark:text-amber-300 dark:border-amber-800' },
};

export const DownloadsView: React.FC = () => {
  const [rows, setRows] = useState<DownloadRow[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState('');

  const reload = useCallback(async () => {
    try {
      setRows(await api.listDownloads());
      setError('');
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    reload();
    // 下载进度持续变化，固定 3s 轮询（有活跃任务时页面停留时间通常较短）
    const timer = setInterval(reload, 3000);
    return () => clearInterval(timer);
  }, [reload]);

  const handleRetry = async (id: string) => {
    try {
      await api.retryDownload(id);
      reload();
    } catch (e: any) {
      setError(e.message);
    }
  };

  const handlePause = async (row: DownloadRow) => {
    if (row.status === 'running' && !window.confirm('将终止当前下载进程并暂停任务，未完成部分需恢复后重新下载，继续？')) return;
    try {
      await api.pauseDownload(row.download_id);
      reload();
    } catch (e: any) {
      setError(e.message);
    }
  };

  const handleDelete = async (row: DownloadRow) => {
    const tip = row.status === 'running' ? '将终止正在进行的下载并移除记录' : '';
    if (tip && !window.confirm(`确定${tip}？`)) return;
    try {
      await api.deleteDownload(row.download_id);
      reload();
    } catch (e: any) {
      setError(e.message);
    }
  };

  const stats = {
    pending: rows.filter((r) => r.status === 'pending').length,
    running: rows.filter((r) => r.status === 'running').length,
    success: rows.filter((r) => r.status === 'success').length,
    failed: rows.filter((r) => r.status === 'failed' || r.status === 'canceled' || r.status === 'paused').length,
  };

  return (
    <div id="downloads-view" className="p-4 sm:p-6 lg:p-8 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
            下载队列
          </h2>
          <p className="text-xs sm:text-sm text-slate-500 dark:text-slate-400 mt-0.5">
            在「收藏数据」详情弹窗中添加下载任务，后端按队列串行执行，3 秒自动刷新。
          </p>
        </div>
        <button
          type="button"
          onClick={reload}
          className="px-3 py-2 rounded-xl bg-white dark:bg-[#161B26] border border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-800 dark:text-slate-200 text-xs font-semibold shadow-2xs inline-flex items-center gap-1.5 transition-colors cursor-pointer"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          手动刷新
        </button>
      </div>

      {error && (
        <div className="px-4 py-3 rounded-2xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 text-xs font-semibold text-rose-700 dark:text-rose-300 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          {error}
        </div>
      )}

      {/* Stats Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          { label: '排队中', value: stats.pending, icon: Clock, cls: 'text-slate-500 dark:text-slate-400' },
          { label: '下载中', value: stats.running, icon: Loader2, cls: 'text-sky-500 dark:text-sky-400' },
          { label: '已完成', value: stats.success, icon: CheckCircle2, cls: 'text-emerald-500 dark:text-emerald-400' },
          { label: '失败 / 暂停', value: stats.failed, icon: AlertTriangle, cls: 'text-rose-500 dark:text-rose-400' },
        ].map((s) => (
          <div
            key={s.label}
            className="bg-white dark:bg-[#161B26] rounded-2xl border border-slate-100 dark:border-slate-800 p-4 flex items-center gap-3"
          >
            <s.icon className={`w-5 h-5 shrink-0 ${s.cls} ${s.label === '下载中' && stats.running > 0 ? 'animate-spin' : ''}`} />
            <div>
              <div className="text-lg font-bold text-slate-900 dark:text-white leading-none">{s.value}</div>
              <div className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">{s.label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Task Table */}
      <div className="bg-white dark:bg-[#161B26] rounded-2xl border border-slate-100 dark:border-slate-800 overflow-hidden">
        {loaded && rows.length === 0 ? (
          <div className="py-16 flex flex-col items-center gap-3 text-slate-400 dark:text-slate-500">
            <Download className="w-10 h-10 opacity-40" />
            <p className="text-xs">队列为空：到「收藏数据」打开内容详情，点击「加入下载队列」</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-slate-400 dark:text-slate-500 border-b border-slate-100 dark:border-slate-800">
                  <th className="px-4 py-3 font-semibold">内容</th>
                  <th className="px-4 py-3 font-semibold">下载器</th>
                  <th className="px-4 py-3 font-semibold">状态</th>
                  <th className="px-4 py-3 font-semibold w-[26%]">进度 / 错误</th>
                  <th className="px-4 py-3 font-semibold">创建时间</th>
                  <th className="px-4 py-3 font-semibold text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr
                    key={r.download_id}
                    className="border-b border-slate-50 dark:border-slate-800/60 last:border-0 hover:bg-slate-50/60 dark:hover:bg-slate-800/30 transition-colors"
                  >
                    <td className="px-4 py-3 max-w-[320px]">
                      <a
                        href={r.url}
                        target="_blank"
                        rel="noreferrer"
                        className="font-semibold text-slate-800 dark:text-slate-200 hover:text-sky-600 dark:hover:text-sky-400 truncate block"
                        title={r.title || r.url}
                      >
                        {r.title || r.content_id || r.url}
                      </a>
                      <span className="text-[10px] text-slate-400 dark:text-slate-500">
                        {r.platform || '—'}
                        {r.output_path && r.status === 'success' && (
                          <span className="inline-flex items-center gap-0.5 ml-1.5" title={r.output_path}>
                            <HardDriveDownload className="w-3 h-3" />
                            已保存到本地
                          </span>
                        )}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-violet-50 dark:bg-violet-950/50 text-violet-700 dark:text-violet-300 border border-violet-100 dark:border-violet-900">
                        {r.downloader}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold border ${STATUS_META[r.status].cls}`}>
                        {r.status === 'running' && <Loader2 className="w-3 h-3 animate-spin" />}
                        {STATUS_META[r.status].label}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {r.status === 'failed' ? (
                        <span
                          className="text-rose-600 dark:text-rose-400 line-clamp-2 block max-w-[360px]"
                          title={r.error_message || ''}
                        >
                          {r.error_message || '未知错误'}
                        </span>
                      ) : (
                        <span className="text-slate-500 dark:text-slate-400 line-clamp-1 block max-w-[360px]" title={r.progress || ''}>
                          {r.progress || '—'}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-slate-400 dark:text-slate-500 whitespace-nowrap">
                      {(r.created_at || '').replace('T', ' ').slice(0, 19)}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1.5">
                        {(r.status === 'pending' || r.status === 'running') && (
                          <button
                            type="button"
                            onClick={() => handlePause(r)}
                            className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400 hover:text-amber-600 dark:hover:text-amber-400 transition-colors cursor-pointer"
                            title={r.status === 'running' ? '终止进程并暂停' : '暂停排队'}
                          >
                            <PauseCircle className="w-3.5 h-3.5" />
                          </button>
                        )}
                        {(r.status === 'failed' || r.status === 'canceled' || r.status === 'paused') && (
                          <button
                            type="button"
                            onClick={() => handleRetry(r.download_id)}
                            className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400 hover:text-sky-600 dark:hover:text-sky-400 transition-colors cursor-pointer"
                            title="重新入队"
                          >
                            {r.status === 'paused' ? <PlayCircle className="w-3.5 h-3.5" /> : <RotateCcw className="w-3.5 h-3.5" />}
                          </button>
                        )}
                        <a
                          href={r.url}
                          target="_blank"
                          rel="noreferrer"
                          className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors"
                          title="打开原站地址"
                        >
                          <ExternalLink className="w-3.5 h-3.5" />
                        </a>
                        <button
                          type="button"
                          onClick={() => handleDelete(r)}
                          className="p-1.5 rounded-lg hover:bg-rose-50 dark:hover:bg-rose-950/40 text-slate-400 hover:text-rose-600 dark:hover:text-rose-400 transition-colors cursor-pointer"
                          title={r.status === 'running' ? '终止并移除' : '移除记录'}
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
