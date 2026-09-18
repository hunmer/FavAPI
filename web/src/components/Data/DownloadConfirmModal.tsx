import React, { useEffect, useState } from 'react';
import { DownloaderId, DOWNLOAD_QUALITIES, qualityLabel } from '../../api';
import { Download, Loader2 } from 'lucide-react';

export interface DownloadConfirmModalProps {
  /** 单条传标题，批量传数量（描述行文案由此拼接） */
  singleTitle?: string;
  count: number;
  /** 全部条目的平台都提供下载直链解析时为 true：显示「平台下载」且默认选中 */
  platformDownload?: boolean;
  /** 清晰度默认值（取设置页「下载清晰度」，缺省 auto） */
  defaultQuality?: string;
  confirming: boolean;
  /** 确认入队；downloader 为用户所选下载器，quality 为所选清晰度 */
  onConfirm: (downloader: DownloaderId, quality: string) => void;
  onClose: () => void;
}

/** 下载确认弹窗（单条/批量共用）：选下载器 + 清晰度后加入下载队列。 */
export const DownloadConfirmModal: React.FC<DownloadConfirmModalProps> = ({
  singleTitle,
  count,
  platformDownload = false,
  defaultQuality = 'auto',
  confirming,
  onConfirm,
  onClose,
}) => {
  const [downloader, setDownloader] = useState<DownloaderId>(
    platformDownload ? 'aria2c' : 'yt-dlp',
  );
  const [quality, setQuality] = useState<string>(defaultQuality);

  useEffect(() => {
    setDownloader(platformDownload ? 'aria2c' : 'yt-dlp');
    setQuality(defaultQuality);
  }, [count, singleTitle, platformDownload, defaultQuality]);

  return (
    <div
      className="fixed inset-0 z-[70] bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 anim-backdrop-enter"
      onClick={() => !confirming && onClose()}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="anim-modal-enter bg-white dark:bg-[#161B26] w-full max-w-sm rounded-[28px] p-6 shadow-2xl border border-slate-100 dark:border-slate-800 space-y-4"
      >
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-2xl bg-sky-50 dark:bg-sky-950 text-sky-600 dark:text-sky-400 flex items-center justify-center shrink-0">
            <Download className="w-5 h-5" />
          </div>
          <h3 className="text-base font-bold text-slate-900 dark:text-white">下载视频</h3>
        </div>
        <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
          {count === 1
            ? singleTitle
              ? <>将下载 <strong className="text-slate-900 dark:text-white">{singleTitle.slice(0, 60)}</strong></>
              : '将下载该条收藏'
            : <>将下载选中的 <strong className="text-slate-900 dark:text-white">{count}</strong> 条收藏</>}
          ，进度可在「下载队列」页查看。
        </p>
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">下载器</span>
          <select
            value={downloader}
            onChange={(e) => setDownloader(e.target.value as DownloaderId)}
            disabled={confirming}
            className="px-2.5 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-xs font-semibold text-slate-700 dark:text-slate-200 bg-white dark:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-400 cursor-pointer disabled:opacity-60"
            title="选择下载器"
          >
            {platformDownload && <option value="aria2c">平台下载 (aria2c)</option>}
            <option value="yt-dlp">yt-dlp</option>
            <option value="videodl">videodl</option>
          </select>
          <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">清晰度</span>
          <select
            value={quality}
            onChange={(e) => setQuality(e.target.value)}
            disabled={confirming}
            className="px-2.5 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-xs font-semibold text-slate-700 dark:text-slate-200 bg-white dark:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-400 cursor-pointer disabled:opacity-60"
            title="平台下载的清晰度（其他下载器忽略此项）"
          >
            {DOWNLOAD_QUALITIES.map((q) => (
              <option key={q} value={q}>{qualityLabel(q)}</option>
            ))}
          </select>
        </div>
        <div className="flex items-center justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={onClose}
            disabled={confirming}
            className="px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300 text-xs font-bold transition-colors disabled:opacity-50 cursor-pointer"
          >
            取消
          </button>
          <button
            type="button"
            onClick={() => onConfirm(downloader, quality)}
            disabled={confirming}
            className="px-4 py-2 rounded-xl bg-sky-600 hover:bg-sky-500 disabled:opacity-60 text-white text-xs font-bold inline-flex items-center gap-1.5 transition-colors active:scale-95 cursor-pointer"
          >
            {confirming && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            {confirming ? '提交中...' : '加入下载队列'}
          </button>
        </div>
      </div>
    </div>
  );
};
