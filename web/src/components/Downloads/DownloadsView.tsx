import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as api from '../../api';
import { DownloadRow, DownloaderId } from '../../api';
import {
  Download,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Loader2,
  Trash2,
  RotateCcw,
  FileText,
  HardDriveDownload,
  PauseCircle,
  PlayCircle,
  FolderOpen,
  X,
  ArrowUp,
  ArrowDown,
  ArrowUpDown,
  ListFilter,
} from 'lucide-react';
import { Popover } from '../Popover';

const STATUS_META: Record<DownloadRow['status'], { label: string; cls: string }> = {
  pending: { label: '排队中', cls: 'bg-slate-100 text-slate-600 border-slate-200 dark:bg-slate-800/60 dark:text-slate-300 dark:border-slate-700' },
  running: { label: '下载中', cls: 'bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-950/50 dark:text-sky-300 dark:border-sky-800' },
  success: { label: '已完成', cls: 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/50 dark:text-emerald-300 dark:border-emerald-800' },
  failed: { label: '失败', cls: 'bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/50 dark:text-rose-300 dark:border-rose-800' },
  canceled: { label: '已取消', cls: 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/50 dark:text-amber-300 dark:border-amber-800' },
  paused: { label: '已暂停', cls: 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/50 dark:text-amber-300 dark:border-amber-800' },
};

const STATUS_KEYS = Object.keys(STATUS_META) as DownloadRow['status'][];
const DOWNLOADER_KEYS: DownloaderId[] = ['yt-dlp', 'videodl', 'aria2c'];

/** 重试确认弹窗（单条/批量共用）：可选择下载引擎；批量时可选「保持原引擎」 */
const RetryConfirmModal: React.FC<{
  rows: DownloadRow[];
  busy: boolean;
  onConfirm: (downloader: DownloaderId | null) => void;
  onClose: () => void;
}> = ({ rows, busy, onConfirm, onClose }) => {
  const single = rows.length === 1;
  const [downloader, setDownloader] = useState<string>(single ? rows[0].downloader : '');

  useEffect(() => {
    setDownloader(single ? rows[0].downloader : '');
  }, [rows, single]);

  return (
    <div
      className="fixed inset-0 z-[70] bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 anim-backdrop-enter"
      onClick={() => !busy && onClose()}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="anim-modal-enter bg-white dark:bg-[#161B26] w-full max-w-sm rounded-[28px] p-6 shadow-2xl border border-slate-100 dark:border-slate-800 space-y-4"
      >
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-2xl bg-sky-50 dark:bg-sky-950 text-sky-600 dark:text-sky-400 flex items-center justify-center shrink-0">
            <RotateCcw className="w-5 h-5" />
          </div>
          <h3 className="text-base font-bold text-slate-900 dark:text-white">重新入队</h3>
        </div>
        <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
          {single ? (
            <>
              将重新下载 <strong className="text-slate-900 dark:text-white">{(rows[0].title || rows[0].content_id || rows[0].url).slice(0, 60)}</strong>
              （当前引擎 {rows[0].downloader}）
            </>
          ) : (
            <>将对 <strong className="text-slate-900 dark:text-white">{rows.length}</strong> 条失败 / 暂停任务重新入队</>
          )}
          ，可先切换下载引擎。
        </p>
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">下载引擎</span>
          <select
            value={downloader}
            onChange={(e) => setDownloader(e.target.value)}
            disabled={busy}
            className="px-2.5 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-xs font-semibold text-slate-700 dark:text-slate-200 bg-white dark:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-400 cursor-pointer disabled:opacity-60"
            title="选择重试使用的下载引擎"
          >
            {!single && <option value="">保持原引擎</option>}
            <option value="yt-dlp">yt-dlp</option>
            <option value="videodl">videodl</option>
            <option value="aria2c">aria2c（平台下载）</option>
          </select>
        </div>
        <div className="flex items-center justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300 text-xs font-bold transition-colors disabled:opacity-50 cursor-pointer"
          >
            取消
          </button>
          <button
            type="button"
            onClick={() => onConfirm(downloader ? (downloader as DownloaderId) : null)}
            disabled={busy}
            className="px-4 py-2 rounded-xl bg-sky-600 hover:bg-sky-500 disabled:opacity-60 text-white text-xs font-bold inline-flex items-center gap-1.5 transition-colors active:scale-95 cursor-pointer"
          >
            {busy && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            {busy ? '提交中...' : `重新入队${single ? '' : ` (${rows.length})`}`}
          </button>
        </div>
      </div>
    </div>
  );
};

/** 筛选下拉菜单：单选；点击已选项等于清除筛选 */
const FilterMenu: React.FC<{
  title: string;
  options: { value: string; label: string }[];
  selected: string | null;
  onSelect: (v: string | null) => void;
}> = ({ title, options, selected, onSelect }) => (
  <div className="text-xs">
    <div className="px-3 py-1.5 text-[10px] font-bold text-slate-400 dark:text-slate-500">{title}</div>
    {[{ value: '', label: '全部' }, ...options].map((o) => {
      const active = o.value ? selected === o.value : selected === null;
      return (
        <button
          key={o.value || '__all__'}
          type="button"
          onClick={() => onSelect(o.value && o.value === selected ? null : o.value || null)}
          className={`w-full text-left px-3 py-1.5 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors cursor-pointer ${
            active ? 'text-sky-600 dark:text-sky-400 font-bold' : 'text-slate-600 dark:text-slate-300'
          }`}
        >
          {o.label}
        </button>
      );
    })}
  </div>
);

/** 下载日志弹窗：读取后端为该任务落盘的 log；任务进行中每 3s 自动刷新 */
const DownloadLogModal: React.FC<{ row: DownloadRow; onClose: () => void }> = ({ row, onClose }) => {
  const [log, setLog] = useState<string | null>(null);
  const [error, setError] = useState('');
  const boxRef = useRef<HTMLPreElement>(null);
  const live = row.status === 'pending' || row.status === 'running';

  const load = useCallback(async () => {
    try {
      setLog((await api.getDownloadLog(row.download_id)).log);
      setError('');
    } catch (e: any) {
      setError(e.message);
    }
  }, [row.download_id]);

  useEffect(() => {
    load();
    if (!live) return;
    const timer = setInterval(load, 3000);
    return () => clearInterval(timer);
  }, [load, live]);

  // 日志持续追加时自动滚到底部
  useEffect(() => {
    if (boxRef.current) boxRef.current.scrollTop = boxRef.current.scrollHeight;
  }, [log]);

  return (
    <div
      id="download-log-backdrop"
      className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 anim-backdrop-enter"
      onClick={onClose}
    >
      <div
        id="download-log-modal"
        onClick={(e) => e.stopPropagation()}
        className="anim-modal-enter bg-white dark:bg-[#161B26] w-full max-w-3xl rounded-[32px] shadow-2xl border border-slate-100 dark:border-slate-800 overflow-hidden flex flex-col max-h-[85vh]"
      >
        {/* Header */}
        <div className="p-5 sm:p-6 bg-slate-50 dark:bg-slate-800 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-10 h-10 rounded-2xl bg-sky-100 dark:bg-sky-950 text-sky-800 dark:text-sky-400 flex items-center justify-center shadow-xs shrink-0">
              <FileText className="w-5 h-5" />
            </div>
            <div className="min-w-0">
              <h3 className="text-base sm:text-lg font-bold text-slate-900 dark:text-white">下载日志</h3>
              <p className="text-xs text-slate-500 dark:text-slate-400 truncate">
                {row.title || row.content_id || row.url} • {STATUS_META[row.status].label}
                {live && ' • 每 3 秒自动刷新'}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="w-8 h-8 rounded-full bg-white dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600 text-slate-700 dark:text-slate-200 flex items-center justify-center transition-colors shadow-2xs cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="p-5 sm:p-6 flex-1 min-h-0 flex flex-col">
          {error ? (
            <div className="py-10 flex flex-col items-center gap-3">
              <p className="text-xs text-rose-600 dark:text-rose-400">{error}</p>
              <button
                type="button"
                onClick={load}
                className="px-4 py-2 bg-slate-900 dark:bg-slate-700 text-white text-xs font-bold rounded-xl cursor-pointer"
              >
                重试读取
              </button>
            </div>
          ) : log === null ? (
            <div className="py-12 flex flex-col items-center gap-3 text-slate-400 dark:text-slate-500">
              <Loader2 className="w-6 h-6 animate-spin" />
              <p className="text-xs">正在读取日志...</p>
            </div>
          ) : log ? (
            <pre
              ref={boxRef}
              className="flex-1 min-h-0 overflow-auto bg-slate-50 dark:bg-slate-900/60 border border-slate-100 dark:border-slate-800 rounded-2xl p-4 text-[11px] leading-5 font-mono text-slate-700 dark:text-slate-300 whitespace-pre-wrap break-all"
            >
              {log}
            </pre>
          ) : (
            <div className="py-12 flex flex-col items-center gap-3 text-slate-400 dark:text-slate-500">
              <FileText className="w-8 h-8 opacity-40" />
              <p className="text-xs">任务尚未开始，暂无日志</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 sm:p-5 bg-slate-50 dark:bg-slate-800 border-t border-slate-100 dark:border-slate-800 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={load}
            className="px-4 py-2 rounded-xl bg-white dark:bg-slate-700 border border-slate-200 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-600 text-slate-700 dark:text-slate-200 text-xs font-bold inline-flex items-center gap-1.5 transition-colors cursor-pointer"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            刷新
          </button>
          <button
            type="button"
            onClick={onClose}
            className="px-5 py-2 bg-slate-900 hover:bg-slate-800 dark:bg-slate-700 dark:hover:bg-slate-600 text-white text-xs font-bold rounded-xl shadow-xs cursor-pointer"
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  );
};

export const DownloadsView: React.FC = () => {
  const [rows, setRows] = useState<DownloadRow[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState('');
  const [logRow, setLogRow] = useState<DownloadRow | null>(null);
  const [retryRows, setRetryRows] = useState<DownloadRow[] | null>(null);
  const [bulkBusy, setBulkBusy] = useState(false);
  /** 创建时间排序：null = 后端默认（最新在前）→ 升序 → 降序 → 默认 */
  const [sortAsc, setSortAsc] = useState<boolean | null>(null);
  const [statusFilter, setStatusFilter] = useState<DownloadRow['status'] | null>(null);
  const [downloaderFilter, setDownloaderFilter] = useState<DownloaderId | null>(null);
  const [filterOpen, setFilterOpen] = useState<'status' | 'downloader' | null>(null);

  const toggleSort = () => setSortAsc((s) => (s === null ? true : s === true ? false : null));

  const sortedRows = useMemo(() => {
    const filtered = rows.filter(
      (r) => (!statusFilter || r.status === statusFilter) && (!downloaderFilter || r.downloader === downloaderFilter),
    );
    if (sortAsc === null) return filtered;
    const dir = sortAsc ? 1 : -1;
    return [...filtered].sort((a, b) => {
      const va = a.created_at ?? '';
      const vb = b.created_at ?? '';
      return va < vb ? -dir : va > vb ? dir : 0;
    });
  }, [rows, sortAsc, statusFilter, downloaderFilter]);

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

  /** 打开输出位置：系统文件管理器定位（成功任务有 output_path 时可用） */
  const handleReveal = async (row: DownloadRow) => {
    try {
      await api.revealDownload(row.download_id);
    } catch (e: any) {
      setError(e.message);
    }
  };

  /** 批量操作：并发调用单条接口，结束后统一刷新并汇报失败数 */
  const runBulk = async (label: string, tasks: Promise<unknown>[]) => {
    if (!tasks.length || bulkBusy) return;
    setBulkBusy(true);
    try {
      const results = await Promise.allSettled(tasks);
      const failedCount = results.filter((r) => r.status === 'rejected').length;
      setError(failedCount ? `【${label}】${failedCount} / ${results.length} 项操作失败` : '');
    } finally {
      setBulkBusy(false);
      reload();
    }
  };

  const retryableRows = rows.filter((r) => r.status === 'failed' || r.status === 'canceled' || r.status === 'paused');
  const successRows = rows.filter((r) => r.status === 'success');

  const handleRetryConfirm = async (downloader: DownloaderId | null) => {
    if (!retryRows) return;
    const targets = retryRows;
    await runBulk('重试', targets.map((r) => api.retryDownload(r.download_id, downloader || undefined)));
    setRetryRows(null);
  };

  const handleClearSuccess = () => {
    if (!window.confirm(`确定移除 ${successRows.length} 条已完成记录？（不删除已下载的本地文件）`)) return;
    runBulk('清空已下载', successRows.map((r) => api.deleteDownload(r.download_id)));
  };

  const handleClearAll = () => {
    if (!window.confirm(`确定清空全部 ${rows.length} 条下载记录？（进行中的任务将被终止，不删除已下载的本地文件）`)) return;
    runBulk('清空全部', rows.map((r) => api.deleteDownload(r.download_id)));
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
        <div className="flex flex-wrap items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={() => setRetryRows(retryableRows)}
            disabled={!retryableRows.length || bulkBusy}
            className="px-3 py-2 rounded-xl bg-white dark:bg-[#161B26] border border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-800 dark:text-slate-200 text-xs font-semibold shadow-2xs inline-flex items-center gap-1.5 transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-white dark:disabled:hover:bg-[#161B26]"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            重试失败{retryableRows.length > 0 && ` (${retryableRows.length})`}
          </button>
          <button
            type="button"
            onClick={handleClearSuccess}
            disabled={!successRows.length || bulkBusy}
            className="px-3 py-2 rounded-xl bg-white dark:bg-[#161B26] border border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-800 dark:text-slate-200 text-xs font-semibold shadow-2xs inline-flex items-center gap-1.5 transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-white dark:disabled:hover:bg-[#161B26]"
          >
            <CheckCircle2 className="w-3.5 h-3.5" />
            清空已下载{successRows.length > 0 && ` (${successRows.length})`}
          </button>
          <button
            type="button"
            onClick={handleClearAll}
            disabled={!rows.length || bulkBusy}
            className="px-3 py-2 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 hover:bg-rose-100 dark:hover:bg-rose-950/60 text-rose-700 dark:text-rose-300 text-xs font-semibold shadow-2xs inline-flex items-center gap-1.5 transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-rose-50 dark:disabled:hover:bg-rose-950/40"
          >
            <Trash2 className="w-3.5 h-3.5" />
            清空全部{rows.length > 0 && ` (${rows.length})`}
          </button>
          <button
            type="button"
            onClick={reload}
            className="px-3 py-2 rounded-xl bg-white dark:bg-[#161B26] border border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-800 dark:text-slate-200 text-xs font-semibold shadow-2xs inline-flex items-center gap-1.5 transition-colors cursor-pointer"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            手动刷新
          </button>
        </div>
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
        ) : sortedRows.length === 0 ? (
          <div className="py-16 flex flex-col items-center gap-3 text-slate-400 dark:text-slate-500">
            <ListFilter className="w-10 h-10 opacity-40" />
            <p className="text-xs">当前筛选条件下没有任务</p>
            <button
              type="button"
              onClick={() => {
                setStatusFilter(null);
                setDownloaderFilter(null);
              }}
              className="px-4 py-2 rounded-xl bg-white dark:bg-[#161B26] border border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-200 text-xs font-semibold transition-colors cursor-pointer"
            >
              清除筛选
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-slate-400 dark:text-slate-500 border-b border-slate-100 dark:border-slate-800">
                  <th className="px-4 py-3 font-semibold">内容</th>
                  <th className="px-4 py-3 font-semibold">
                    <Popover
                      open={filterOpen === 'downloader'}
                      onClose={() => setFilterOpen(null)}
                      fixed
                      panelClassName="bg-white dark:bg-[#161B26] border border-slate-100 dark:border-slate-800 rounded-2xl shadow-xl py-1 min-w-[120px]"
                      content={
                        <FilterMenu
                          title="下载器"
                          options={DOWNLOADER_KEYS.map((d) => ({ value: d, label: d }))}
                          selected={downloaderFilter}
                          onSelect={(v) => {
                            setDownloaderFilter(v as DownloaderId | null);
                            setFilterOpen(null);
                          }}
                        />
                      }
                    >
                      <button
                        type="button"
                        onClick={() => setFilterOpen(filterOpen === 'downloader' ? null : 'downloader')}
                        className={`inline-flex items-center gap-1 cursor-pointer transition-colors ${
                          downloaderFilter
                            ? 'text-sky-600 dark:text-sky-400'
                            : 'hover:text-slate-600 dark:hover:text-slate-300'
                        }`}
                        title="筛选下载器"
                      >
                        下载器
                        <ListFilter className="w-3 h-3" />
                      </button>
                    </Popover>
                  </th>
                  <th className="px-4 py-3 font-semibold">
                    <Popover
                      open={filterOpen === 'status'}
                      onClose={() => setFilterOpen(null)}
                      fixed
                      panelClassName="bg-white dark:bg-[#161B26] border border-slate-100 dark:border-slate-800 rounded-2xl shadow-xl py-1 min-w-[120px]"
                      content={
                        <FilterMenu
                          title="状态"
                          options={STATUS_KEYS.map((s) => ({ value: s, label: STATUS_META[s].label }))}
                          selected={statusFilter}
                          onSelect={(v) => {
                            setStatusFilter(v as DownloadRow['status'] | null);
                            setFilterOpen(null);
                          }}
                        />
                      }
                    >
                      <button
                        type="button"
                        onClick={() => setFilterOpen(filterOpen === 'status' ? null : 'status')}
                        className={`inline-flex items-center gap-1 cursor-pointer transition-colors ${
                          statusFilter
                            ? 'text-sky-600 dark:text-sky-400'
                            : 'hover:text-slate-600 dark:hover:text-slate-300'
                        }`}
                        title="筛选状态"
                      >
                        状态
                        <ListFilter className="w-3 h-3" />
                      </button>
                    </Popover>
                  </th>
                  <th className="px-4 py-3 font-semibold w-[26%]">进度 / 错误</th>
                  <th
                    onClick={toggleSort}
                    title="点击切换排序"
                    className="px-4 py-3 font-semibold cursor-pointer select-none hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
                  >
                    <span className="inline-flex items-center gap-1">
                      创建时间
                      {sortAsc === null ? (
                        <ArrowUpDown className="w-3 h-3 opacity-30" />
                      ) : sortAsc ? (
                        <ArrowUp className="w-3 h-3" />
                      ) : (
                        <ArrowDown className="w-3 h-3" />
                      )}
                    </span>
                  </th>
                  <th className="px-4 py-3 font-semibold text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {sortedRows.map((r) => (
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
                            onClick={() => setRetryRows([r])}
                            className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400 hover:text-sky-600 dark:hover:text-sky-400 transition-colors cursor-pointer"
                            title="重新入队（可选择下载引擎）"
                          >
                            {r.status === 'paused' ? <PlayCircle className="w-3.5 h-3.5" /> : <RotateCcw className="w-3.5 h-3.5" />}
                          </button>
                        )}
                        {r.output_path && (
                          <button
                            type="button"
                            onClick={() => handleReveal(r)}
                            className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400 hover:text-emerald-600 dark:hover:text-emerald-400 transition-colors cursor-pointer"
                            title={`打开输出位置：${r.output_path}`}
                          >
                            <FolderOpen className="w-3.5 h-3.5" />
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => setLogRow(r)}
                          className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400 hover:text-sky-600 dark:hover:text-sky-400 transition-colors cursor-pointer"
                          title="查看下载日志"
                        >
                          <FileText className="w-3.5 h-3.5" />
                        </button>
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

      {/* 弹窗用最新行数据：状态实时更新，任务结束后自动停止轮询 */}
      {logRow && (
        <DownloadLogModal
          row={rows.find((r) => r.download_id === logRow.download_id) || logRow}
          onClose={() => setLogRow(null)}
        />
      )}

      {retryRows && retryRows.length > 0 && (
        <RetryConfirmModal
          rows={retryRows}
          busy={bulkBusy}
          onConfirm={handleRetryConfirm}
          onClose={() => !bulkBusy && setRetryRows(null)}
        />
      )}
    </div>
  );
};
