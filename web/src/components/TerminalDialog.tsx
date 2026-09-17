/**
 * 终端样式对话框：实时流式展示后端命令输出（pip 安装/更新 yt-dlp、videodl）。
 * 由 downloader prop 驱动：非 null 时打开并自动发起流式请求，结束后回调 onFinished。
 */
import React, { useEffect, useRef, useState } from 'react';
import { Loader2, X, CheckCircle2, AlertTriangle } from 'lucide-react';
import { DownloaderId, ToolchainUpdateEvent, updateToolchainStream } from '../api';

interface TerminalDialogProps {
  downloader: DownloaderId | null; // null = 关闭
  onClose: () => void;
  onFinished: () => void; // done/error 后通知刷新安装状态
}

type RunResult =
  | { status: 'done'; before: string | null; after: string | null; updated: boolean }
  | { status: 'error'; message: string };

export const TerminalDialog: React.FC<TerminalDialogProps> = ({ downloader, onClose, onFinished }) => {
  const [lines, setLines] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<RunResult | null>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  // StrictMode 下 effect 会双跑，用 ref 保证同一个 downloader 只发起一次请求
  const startedForRef = useRef<string | null>(null);

  useEffect(() => {
    if (!downloader || startedForRef.current === downloader) return;
    startedForRef.current = downloader;
    setLines([]);
    setResult(null);
    setRunning(true);
    updateToolchainStream(downloader, (ev: ToolchainUpdateEvent) => {
      if (ev.type === 'line') setLines((prev) => [...prev, ev.text]);
    })
      .then((final) => {
        setResult(
          final?.type === 'done'
            ? { status: 'done', before: final.before, after: final.after, updated: final.updated }
            : { status: 'error', message: '连接中断，输出未正常结束' }
        );
        onFinished();
      })
      .catch((err: any) => {
        setResult({ status: 'error', message: err?.message || '未知错误' });
        onFinished();
      })
      .finally(() => setRunning(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [downloader]);

  // 新输出时自动滚动到底部
  useEffect(() => {
    const el = bodyRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines]);

  const handleClose = () => {
    if (running) return; // 执行中禁止关闭（关闭会终止后端安装进程）
    startedForRef.current = null;
    onClose();
  };

  if (!downloader) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="w-full max-w-2xl flex flex-col max-h-[80vh] bg-white dark:bg-[#161B26] rounded-2xl border border-slate-200 dark:border-slate-700 shadow-2xl">
        {/* 标题栏：终端三点 + 标题 + 状态 */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100 dark:border-slate-800">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="flex items-center gap-1.5 shrink-0">
              <span className="w-3 h-3 rounded-full bg-rose-500" />
              <span className="w-3 h-3 rounded-full bg-amber-400" />
              <span className="w-3 h-3 rounded-full bg-emerald-500" />
            </div>
            <span className="text-sm font-bold text-slate-900 dark:text-white truncate font-mono">
              pip install --upgrade {downloader === 'videodl' ? 'videofetch' : 'yt-dlp'}
            </span>
          </div>
          {running ? (
            <span className="flex items-center gap-1.5 text-[11px] font-semibold text-sky-500 shrink-0">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              执行中...
            </span>
          ) : (
            <button
              type="button"
              onClick={handleClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer"
              title="关闭"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>

        {/* 终端输出区 */}
        <div
          ref={bodyRef}
          className="flex-1 overflow-y-auto m-4 mb-2 rounded-xl bg-[#0C111C] border border-slate-800 p-3.5 font-mono text-[11px] leading-relaxed text-slate-300 whitespace-pre-wrap break-all"
        >
          {lines.length === 0 ? (
            <span className="text-slate-500">$ 等待输出...</span>
          ) : (
            lines.map((l, i) => (
              <div key={i} className={l.startsWith('ERROR') || /^(Requirement already satisfied|ERROR)/.test(l) ? 'text-amber-300' : undefined}>
                {l}
              </div>
            ))
          )}
          {running && <span className="inline-block w-2 h-3.5 bg-emerald-400 animate-pulse align-middle ml-0.5" />}
        </div>

        {/* 底部状态栏 */}
        <div className="flex items-center justify-between gap-3 px-4 py-3 border-t border-slate-100 dark:border-slate-800">
          {result?.status === 'done' ? (
            <span className="text-xs font-semibold text-emerald-600 dark:text-emerald-400 flex items-center gap-1.5 min-w-0">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              {result.updated
                ? `已更新：${result.before ?? '未安装'} → ${result.after ?? '未知'}`
                : `已是最新版本（${result.after ?? '未知'}）`}
            </span>
          ) : result?.status === 'error' ? (
            <span className="text-xs font-semibold text-rose-500 flex items-center gap-1.5 min-w-0">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span className="truncate">{result.message}</span>
            </span>
          ) : (
            <span className="text-[11px] text-slate-400">安装过程中请勿关闭窗口（关闭将终止安装进程）</span>
          )}

          <button
            type="button"
            onClick={handleClose}
            disabled={running}
            className="px-4 py-1.5 rounded-xl bg-slate-900 dark:bg-sky-600 hover:bg-slate-800 dark:hover:bg-sky-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-bold transition-colors shrink-0 cursor-pointer"
          >
            {running ? '执行中...' : '关闭'}
          </button>
        </div>
      </div>
    </div>
  );
};
