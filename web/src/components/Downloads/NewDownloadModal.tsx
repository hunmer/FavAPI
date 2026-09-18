import React, { useMemo, useState } from 'react';
import { motion } from 'motion/react';
import { Download } from 'lucide-react';
import * as api from '../../api';
import { Account } from '../../types';
import { PLATFORMS } from '../../data/platforms';

interface NewDownloadModalProps {
  accounts: Account[];
  showToast: (msg: string, type?: 'success' | 'info' | 'error') => void;
  onClose: () => void;
}

const DOWNLOADERS: { id: api.DownloaderId; label: string; hint: string }[] = [
  { id: 'yt-dlp', label: 'yt-dlp', hint: '通用视频下载（YouTube/B站等）' },
  { id: 'videodl', label: 'videodl', hint: '备用通用下载器' },
  { id: 'aria2c', label: '平台下载（aria2c）', hint: '按平台 API 解析直链（抖音/快手/B站/ TikTok）' },
];

/** 新建下载任务弹窗（下载页 Header「新建下载」入口）：按内容 ID 直接入队。 */
export const NewDownloadModal: React.FC<NewDownloadModalProps> = ({ accounts, showToast, onClose }) => {
  const supported = useMemo(() => PLATFORMS.filter((p) => p.isSupported), []);
  const [form, setForm] = useState({
    platform: supported[0]?.id || 'douyin',
    content_id: '',
    title: '',
    downloader: 'yt-dlp' as api.DownloaderId,
    account_id: '',
    quality: '',
  });
  const [busy, setBusy] = useState(false);

  const platformAccounts = useMemo(
    () => accounts.filter((a) => a.platform === form.platform && a.status === 'active'),
    [accounts, form.platform]
  );

  const submit = async () => {
    if (!form.content_id.trim()) return;
    setBusy(true);
    try {
      const row = await api.createDownload({
        content_id: form.content_id.trim(),
        platform: form.platform,
        title: form.title.trim(),
        downloader: form.downloader,
        account_id: form.account_id,
        quality: form.quality.trim() || undefined,
      });
      showToast(`下载任务已创建：${row.title || row.content_id}`);
      onClose();
    } catch (e: any) {
      showToast(e.message || '创建下载任务失败', 'error');
    } finally {
      setBusy(false);
    }
  };

  const inputCls =
    'w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 text-sm bg-transparent dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-slate-900 dark:focus:ring-sky-500';

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4"
      onClick={() => !busy && onClose()}
    >
      <motion.div
        initial={{ scale: 0.95, y: 12 }}
        animate={{ scale: 1, y: 0 }}
        exit={{ scale: 0.95, y: 12 }}
        transition={{ type: 'spring', stiffness: 320, damping: 30 }}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-md bg-white dark:bg-[#161B26] rounded-[28px] p-6 shadow-2xl border border-slate-100 dark:border-slate-800 space-y-4"
      >
        <h3 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
          <Download className="w-4 h-4 text-sky-500" />
          新建下载任务
        </h3>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5">平台</label>
            <select
              value={form.platform}
              onChange={(e) => setForm((f) => ({ ...f, platform: e.target.value, account_id: '' }))}
              className={inputCls + ' cursor-pointer'}
            >
              {supported.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5">
              内容 ID <span className="text-rose-500">*</span>
            </label>
            <input
              value={form.content_id}
              onChange={(e) => setForm((f) => ({ ...f, content_id: e.target.value }))}
              placeholder="如 7665364150679587323 / BV1xx…"
              className={inputCls + ' font-mono text-xs'}
            />
          </div>
        </div>

        <div>
          <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5">标题（可选）</label>
          <input
            value={form.title}
            onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
            placeholder="留空使用内容 ID"
            className={inputCls}
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5">下载引擎</label>
            <select
              value={form.downloader}
              onChange={(e) => setForm((f) => ({ ...f, downloader: e.target.value as api.DownloaderId }))}
              className={inputCls + ' cursor-pointer'}
            >
              {DOWNLOADERS.map((d) => (
                <option key={d.id} value={d.id}>{d.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5">来源账号（可选）</label>
            <select
              value={form.account_id}
              onChange={(e) => setForm((f) => ({ ...f, account_id: e.target.value }))}
              className={inputCls + ' cursor-pointer'}
            >
              <option value="">不指定</option>
              {platformAccounts.map((a) => (
                <option key={a.id} value={a.id}>{a.name}</option>
              ))}
            </select>
          </div>
        </div>
        <p className="text-[11px] text-slate-400 -mt-2">
          {DOWNLOADERS.find((d) => d.id === form.downloader)?.hint}
          {form.downloader === 'aria2c' && '，建议选择来源账号（解析直链需其登录态）'}
        </p>

        <div>
          <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5">清晰度（可选）</label>
          <input
            value={form.quality}
            onChange={(e) => setForm((f) => ({ ...f, quality: e.target.value }))}
            placeholder="auto = 平台推荐；或高度如 1080"
            className={inputCls}
          />
        </div>

        <div className="flex justify-end gap-2 pt-1">
          <button
            onClick={() => !busy && onClose()}
            className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 transition-colors cursor-pointer"
          >
            取消
          </button>
          <button
            onClick={submit}
            disabled={busy || !form.content_id.trim()}
            className="px-5 py-2 rounded-xl text-xs font-bold bg-slate-900 dark:bg-sky-600 text-white hover:opacity-90 active:scale-95 transition-all disabled:opacity-50 inline-flex items-center gap-1.5 cursor-pointer"
          >
            {busy && <span className="w-3 h-3 border-2 border-white/40 border-t-white rounded-full animate-spin" />}
            {busy ? '创建中…' : '加入下载队列'}
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
};
