import React, { useEffect, useRef, useState } from 'react';
import { Link2, Loader2, ImagePlus, X } from 'lucide-react';
import * as api from '../../api';

/** 录入结果（附带封面上传状态，供父组件 toast 提示） */
export interface ManualItemCreated extends api.ManualFavoriteResult {
  /** coverUploaded：已选封面时的上传结果（未选封面为 undefined） */
  coverUploaded?: boolean;
}

/** 手动录入链接弹窗（自 BrowserToolbar 触发）：URL 必填，标题/备注/封面可选，提交后入收藏库 */
export const BrowserManualItemModal: React.FC<{
  onClose: () => void;
  onCreated: (r: ManualItemCreated) => void;
}> = ({ onClose, onCreated }) => {
  const [url, setUrl] = useState('');
  const [title, setTitle] = useState('');
  const [note, setNote] = useState('');
  const [coverFile, setCoverFile] = useState<File | null>(null);
  const [coverPreview, setCoverPreview] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 预览 URL 生命周期：换图/卸载时释放，避免泄漏
  useEffect(() => () => { if (coverPreview) URL.revokeObjectURL(coverPreview); }, [coverPreview]);

  const pickCover = (file: File | undefined) => {
    if (!file) return;
    if (!/^image\/(jpeg|png|webp|gif)$/.test(file.type)) {
      setError('封面仅支持 jpg / png / webp / gif 图片');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setError('封面超过 10MB 上限');
      return;
    }
    setError('');
    if (coverPreview) URL.revokeObjectURL(coverPreview);
    setCoverFile(file);
    setCoverPreview(URL.createObjectURL(file));
  };

  const clearCover = () => {
    URL.revokeObjectURL(coverPreview);
    setCoverFile(null);
    setCoverPreview('');
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const submit = async () => {
    const trimmed = url.trim();
    if (!trimmed || saving) return;
    setSaving(true);
    setError('');
    try {
      const r = await api.createManualFavorite({ url: trimmed, title: title.trim(), note: note.trim() });
      // 条目已入库；封面上传失败不阻断，结果带回父组件提示
      let coverUploaded: boolean | undefined;
      if (coverFile) {
        try {
          await api.uploadCover(r.platform, r.content_id, coverFile);
          coverUploaded = true;
        } catch {
          coverUploaded = false;
        }
      }
      onCreated({ ...r, coverUploaded });
    } catch (err: any) {
      setError(err?.message || '录入失败');
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[70] bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 anim-backdrop-enter"
      onClick={() => !saving && onClose()}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="anim-modal-enter bg-white dark:bg-[#161B26] w-full max-w-sm rounded-[28px] shadow-2xl border border-slate-100 dark:border-slate-800 overflow-hidden"
      >
        <div className="p-5 bg-slate-50 dark:bg-slate-800 border-b border-slate-100 dark:border-slate-800">
          <h3 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
            <Link2 className="w-4 h-4 text-violet-600" />
            手动录入链接
          </h3>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            链接不经过平台抓取，直接入收藏库（来源标记「手动录入」）
          </p>
        </div>
        <div className="p-5 space-y-3">
          <div className="space-y-1.5">
            <span className="text-xs font-bold text-slate-600 dark:text-slate-400">链接</span>
            <input
              autoFocus
              type="text"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && submit()}
              placeholder="https://example.com/page（无协议自动补 https）"
              className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 text-sm dark:bg-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-violet-600"
            />
          </div>
          <div className="space-y-1.5">
            <span className="text-xs font-bold text-slate-600 dark:text-slate-400">标题（可选）</span>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="留空时以链接作为标题"
              className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 text-sm dark:bg-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-violet-600"
            />
          </div>
          <div className="space-y-1.5">
            <span className="text-xs font-bold text-slate-600 dark:text-slate-400">备注（可选）</span>
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
              placeholder="为什么收藏这条内容"
              className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 text-sm dark:bg-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-violet-600 resize-none"
            />
          </div>
          <div className="space-y-1.5">
            <span className="text-xs font-bold text-slate-600 dark:text-slate-400">封面（可选）</span>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp,image/gif"
              className="hidden"
              onChange={(e) => pickCover(e.target.files?.[0])}
            />
            {coverPreview ? (
              <div className="relative w-fit">
                <img
                  src={coverPreview}
                  alt="封面预览"
                  className="max-h-28 max-w-full rounded-xl border border-slate-200 dark:border-slate-700 object-cover"
                />
                <button
                  type="button"
                  onClick={clearCover}
                  disabled={saving}
                  title="移除封面"
                  className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-slate-900/80 hover:bg-slate-900 text-white flex items-center justify-center cursor-pointer"
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={saving}
                className="w-full py-2.5 rounded-xl border border-dashed border-slate-300 dark:border-slate-600 text-xs font-semibold text-slate-500 dark:text-slate-400 hover:border-violet-400 hover:text-violet-600 flex items-center justify-center gap-1.5 transition-all cursor-pointer"
              >
                <ImagePlus className="w-3.5 h-3.5" />
                选择图片（jpg / png / webp / gif，最大 10MB）
              </button>
            )}
          </div>
          {error && <p className="text-[11px] text-rose-600 break-all">{error}</p>}
          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              disabled={saving}
              className="px-4 py-2 text-xs font-semibold text-slate-600 dark:text-slate-300 hover:text-slate-800 dark:hover:text-slate-100 rounded-xl cursor-pointer"
            >
              取消
            </button>
            <button
              type="button"
              onClick={submit}
              disabled={saving || !url.trim()}
              className="px-4 py-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white text-xs font-bold rounded-xl flex items-center gap-1.5 cursor-pointer"
            >
              {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Link2 className="w-3.5 h-3.5" />}
              {saving ? '录入中...' : '添加到收藏库'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
