import React, { useEffect, useState } from 'react';
import { ScrapedItem } from '../../types';
import * as api from '../../api';
import { DownloaderId } from '../../api';
import { ExternalLink, X, Pencil, Plus, CheckCircle2, Download, Loader2 } from 'lucide-react';

interface ItemDetailModalProps {
  item: ScrapedItem;
  onClose: () => void;
  onSaveTags?: (tags: string[]) => Promise<void>;
}

export const ItemDetailModal: React.FC<ItemDetailModalProps> = ({ item, onClose, onSaveTags }) => {
  const [editing, setEditing] = useState(false);
  const [draftTags, setDraftTags] = useState<string[]>([]);
  const [input, setInput] = useState('');
  const [saving, setSaving] = useState(false);

  // 下载队列：downloader 选择 + 入队状态（切换内容时复位）
  const [downloader, setDownloader] = useState<DownloaderId>('yt-dlp');
  const [adding, setAdding] = useState(false);
  const [added, setAdded] = useState(false);
  useEffect(() => {
    setDownloader('yt-dlp');
    setAdding(false);
    setAdded(false);
  }, [item.id]);

  const addDownload = async () => {
    if (adding) return;
    setAdding(true);
    try {
      await api.createDownload({
        content_id: item.id,
        platform: item.platform,
        account_id: item.accountId || '',
        title: item.title,
        url: item.url.startsWith('http') ? item.url : '',
        downloader,
      });
      setAdded(true);
    } catch (err: any) {
      alert(`加入下载队列失败：${err?.message || '未知错误'}`);
    } finally {
      setAdding(false);
    }
  };

  const enterEdit = () => {
    setDraftTags(item.tags || []);
    setInput('');
    setEditing(true);
  };

  const addInputTag = () => {
    const t = input.trim().replace(/^#+/, '');
    if (t && !draftTags.includes(t)) {
      setDraftTags((prev) => [...prev, t]);
    }
    setInput('');
  };

  const save = async () => {
    if (!onSaveTags || saving) return;
    setSaving(true);
    try {
      await onSaveTags(draftTags);
      setEditing(false);
    } catch (err: any) {
      alert(`标签保存失败：${err?.message || '未知错误'}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 anim-backdrop-enter"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="anim-modal-enter relative bg-white dark:bg-[#161B26] w-full max-w-lg lg:max-w-4xl rounded-[32px] shadow-2xl border border-slate-100 dark:border-slate-800 overflow-hidden flex flex-col lg:flex-row h-[75vh]"
      >
        {/* Cover preview: 跟随图片原始比例，不裁切；宽屏撑满弹窗固定高，contain 居中于黑底 */}
        <div className="relative bg-slate-900 lg:w-1/2 lg:shrink-0">
          {item.coverUrl ? <img
            src={item.coverUrl}
            alt=""
            className="w-full h-auto max-h-[40vh] lg:h-full lg:max-h-none object-contain"
            referrerPolicy="no-referrer"
          /> : <div className="w-full h-48 lg:h-full flex items-center justify-center text-slate-400 text-sm">暂无封面</div>}
        </div>

        <button
          type="button"
          onClick={onClose}
          className="absolute top-3 right-3 z-10 w-8 h-8 rounded-full bg-black/60 hover:bg-black/80 text-white flex items-center justify-center backdrop-blur-xs"
        >
          <X className="w-4 h-4" />
        </button>

        {/* Detail panel: 宽屏下绝对定位撑满弹窗（高度跟随封面图），底行固定不滚动 */}
        <div className="flex flex-col flex-1 min-h-0 p-6 gap-4 lg:absolute lg:inset-y-0 lg:right-0 lg:w-1/2">
          <div className="flex-1 min-h-0 overflow-y-auto space-y-4">
            <div>
              <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-indigo-50 dark:bg-indigo-950 text-indigo-700 dark:text-indigo-400 border border-indigo-200 dark:border-indigo-800">
                {item.folderName}
              </span>
              <h3 className="text-base font-bold text-slate-900 dark:text-white mt-2">
                {item.title}
              </h3>
            </div>

            <div className="grid grid-cols-2 gap-3 text-xs bg-slate-50 dark:bg-slate-800 p-4 rounded-2xl border border-slate-100 dark:border-slate-700">
              <div>
                <span className="text-slate-400">作者 / UP主</span>
                <div className="font-semibold text-slate-800 dark:text-slate-200 mt-0.5">{item.author}</div>
              </div>
              <div>
                <span className="text-slate-400">内容时长</span>
                <div className="font-semibold text-slate-800 dark:text-slate-200 mt-0.5">{item.duration || '—'}</div>
              </div>
              <div>
                <span className="text-slate-400">收藏时间</span>
                <div className="font-semibold text-slate-800 dark:text-slate-200 mt-0.5">{item.favTime}</div>
              </div>
              <div>
                <span className="text-slate-400">抓取入库时间</span>
                <div className="font-semibold text-slate-800 dark:text-slate-200 mt-0.5">{item.crawlTime}</div>
              </div>
            </div>
            {item.notes && <div className="text-sm text-slate-600 dark:text-slate-300 whitespace-pre-wrap bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700 rounded-xl p-3">{item.notes}</div>}

            {/* 媒体标签：查看 / 手动编辑两种模式 */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-xs font-bold text-slate-500 dark:text-slate-400">媒体标签</span>
                {onSaveTags && !editing && (
                  <button
                    type="button"
                    onClick={enterEdit}
                    className="text-[11px] font-semibold text-slate-400 hover:text-violet-600 inline-flex items-center gap-1 transition-colors cursor-pointer"
                  >
                    <Pencil className="w-3 h-3" />
                    手动打标
                  </button>
                )}
              </div>

              {editing ? (
                <div className="space-y-2.5">
                  <div className="flex flex-wrap gap-1.5">
                    {draftTags.length === 0 && (
                      <span className="text-[11px] text-slate-400">暂无标签，在下方输入添加</span>
                    )}
                    {draftTags.map((t) => (
                      <span
                        key={t}
                        className="group/tag inline-flex items-center gap-1 pl-2 pr-1 py-0.5 rounded-md bg-violet-50 dark:bg-violet-950 text-violet-700 dark:text-violet-400 text-xs border border-violet-100 dark:border-violet-900"
                      >
                        #{t}
                        <button
                          type="button"
                          onClick={() => setDraftTags((prev) => prev.filter((x) => x !== t))}
                          className="w-4 h-4 rounded-full hover:bg-violet-200 text-violet-400 hover:text-rose-600 flex items-center justify-center transition-colors cursor-pointer"
                          title="移除"
                        >
                          <X className="w-2.5 h-2.5" />
                        </button>
                      </span>
                    ))}
                  </div>
                  <div className="flex gap-1.5">
                    <input
                      type="text"
                      value={input}
                      onChange={(e) => setInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault();
                          addInputTag();
                        }
                      }}
                      placeholder="输入新标签，回车添加"
                      className="flex-1 px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 text-xs bg-transparent dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-violet-500"
                    />
                    <button
                      type="button"
                      onClick={addInputTag}
                      className="px-2.5 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300 transition-colors cursor-pointer"
                      title="添加"
                    >
                      <Plus className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <div className="flex items-center justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => setEditing(false)}
                      disabled={saving}
                      className="px-3 py-1.5 text-xs font-semibold text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 cursor-pointer"
                    >
                      取消
                    </button>
                    <button
                      type="button"
                      onClick={save}
                      disabled={saving}
                      className="px-3.5 py-1.5 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white text-xs font-bold rounded-lg inline-flex items-center gap-1.5 cursor-pointer"
                    >
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      {saving ? '保存中...' : '保存标签'}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {item.tags && item.tags.length > 0 ? (
                    item.tags.map((t) => (
                      <span key={t} className="px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 text-xs">
                        #{t}
                      </span>
                    ))
                  ) : (
                    <span className="text-[11px] text-slate-400">
                      暂无标签，可点击上方「手动打标」添加
                    </span>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* 固定底行：不参与滚动 */}
          <div className="shrink-0 pt-3 border-t border-slate-100 dark:border-slate-800 space-y-2.5">
            {/* 加入下载队列：选择下载器后入队，进度在「下载队列」页查看 */}
            <div className="flex items-center gap-2">
              <select
                value={downloader}
                onChange={(e) => setDownloader(e.target.value as DownloaderId)}
                disabled={added}
                className="px-2.5 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-xs font-semibold text-slate-700 dark:text-slate-200 bg-white dark:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-400 cursor-pointer disabled:opacity-60"
                title="选择下载器"
              >
                <option value="yt-dlp">yt-dlp</option>
                <option value="videodl">videodl</option>
              </select>
              <button
                type="button"
                onClick={addDownload}
                disabled={adding || added}
                className="flex-1 px-4 py-2 bg-sky-600 hover:bg-sky-500 disabled:opacity-60 disabled:hover:bg-sky-600 text-white text-xs font-bold rounded-xl shadow-xs inline-flex items-center justify-center gap-1.5 cursor-pointer transition-colors"
              >
                {added ? (
                  <CheckCircle2 className="w-3.5 h-3.5" />
                ) : adding ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Download className="w-3.5 h-3.5" />
                )}
                {added ? '已加入下载队列' : adding ? '提交中...' : '加入下载队列'}
              </button>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-slate-400">
                归属账号: {item.accountName}
              </span>
              {item.url ? (
                <a
                  href={item.url}
                  target="_blank"
                  rel="noreferrer"
                  className="px-4 py-2 bg-slate-900 hover:bg-slate-800 dark:bg-slate-700 dark:hover:bg-slate-600 text-white text-xs font-bold rounded-xl shadow-xs inline-flex items-center gap-1.5"
                >
                  前往原站页面
                  <ExternalLink className="w-3.5 h-3.5" />
                </a>
              ) : (
                <span
                  title="该条目没有可用的原站链接"
                  className="px-4 py-2 bg-slate-400 text-white text-xs font-bold rounded-xl inline-flex items-center gap-1.5 cursor-not-allowed opacity-70"
                >
                  无原站链接
                  <ExternalLink className="w-3.5 h-3.5" />
                </span>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
