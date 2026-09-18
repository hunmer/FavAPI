import React, { useRef, useState } from 'react';
import { RefreshCw, X } from 'lucide-react';
import * as api from '../../api';

interface FollowsSyncButtonProps {
  showToast: (msg: string, type?: 'success' | 'info' | 'error') => void;
  /** 同步落终态后回调（父级触发列表刷新） */
  onDone: () => void;
}

/** 全局 Header 右侧的「一键更新最新视频」按钮（仅特别关注页注入）：
 *  SSE 流式逐博主推送进度（按钮实时显示 N/M · 新增 X），可中途取消；完成 toast 汇总。 */
export const FollowsSyncButton: React.FC<FollowsSyncButtonProps> = ({ showToast, onDone }) => {
  const [progress, setProgress] = useState<{ done: number; total: number; newCount: number } | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const syncing = progress !== null;

  const run = async () => {
    if (syncing) return;
    setProgress({ done: 0, total: 0, newCount: 0 });
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const res = await api.syncFollowPostsStream(
        {},
        (ev) => setProgress({ done: ev.done, total: ev.total, newCount: ev.new }),
        controller.signal
      );
      const failed = res.results.filter((r) => r.status === 'failed');
      if (failed.length) {
        showToast(
          `同步完成：${res.ok}/${res.total} 位博主，新增 ${res.new} 条；失败：${failed
            .slice(0, 3)
            .map((f) => f.nickname || f.sec_uid.slice(0, 8))
            .join('、')}${failed.length > 3 ? ' 等' : ''}`,
          'error'
        );
      } else {
        showToast(`同步完成：${res.ok} 位博主，本次新增 ${res.new} 条作品`);
      }
    } catch (e: any) {
      if (controller.signal.aborted) {
        showToast('已取消同步（已完成的博主作品保留入库）', 'info');
      } else {
        showToast(e.message || '同步失败', 'error');
      }
    } finally {
      abortRef.current = null;
      setProgress(null);
      onDone();
    }
  };

  const label = syncing
    ? `更新中 ${progress!.done}/${progress!.total || '?'} · 新增 ${progress!.newCount}`
    : '一键更新最新视频';

  return (
    <button
      onClick={syncing ? () => abortRef.current?.abort() : run}
      title={syncing ? '点击取消同步（已完成的保留）' : '逐特别关注博主拉取最新作品并入库'}
      className={`flex items-center gap-1.5 px-3 sm:px-3.5 py-1.5 rounded-full text-xs font-semibold border transition-all active:scale-95 cursor-pointer ${
        syncing
          ? 'bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300 border-emerald-300 dark:border-emerald-800'
          : 'bg-emerald-50 dark:bg-emerald-950/50 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800 hover:bg-emerald-100 dark:hover:bg-emerald-950'
      }`}
    >
      {syncing ? <X className="w-3.5 h-3.5 shrink-0" /> : <RefreshCw className="w-3.5 h-3.5 shrink-0" />}
      <span className="hidden sm:inline whitespace-nowrap">{label}</span>
      {syncing && <span className="sm:hidden whitespace-nowrap font-mono">{progress!.done}/{progress!.total || '?'}</span>}
    </button>
  );
};
