import React from 'react';
import { AlertTriangle, Trash2 } from 'lucide-react';
import { ScrapedItem } from '../../types';

/** 批量删除收藏确认（多选模式，自 DataBrowserView 抽离） */
export const BrowserItemsDeleteModal: React.FC<{
  count: number;
  deleting: boolean;
  onClose: () => void;
  onConfirm: () => void;
}> = ({ count, deleting, onClose, onConfirm }) => (
  <div
    className="fixed inset-0 z-[70] bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 anim-backdrop-enter"
    onClick={() => !deleting && onClose()}
  >
    <div
      onClick={(e) => e.stopPropagation()}
      className="anim-modal-enter bg-white dark:bg-[#161B26] w-full max-w-sm rounded-[28px] p-6 shadow-2xl border border-slate-100 dark:border-slate-800 space-y-4"
    >
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-2xl bg-rose-50 dark:bg-rose-950 text-rose-600 dark:text-rose-400 flex items-center justify-center shrink-0">
          <AlertTriangle className="w-5 h-5" />
        </div>
        <h3 className="text-base font-bold text-slate-900 dark:text-white">批量删除收藏</h3>
      </div>
      <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
        确定删除已选中的{' '}
        <strong className="text-rose-600">{count}</strong> 条收藏吗？
        删除后将从收藏列表移除（不可恢复），内容元数据保留。
      </p>
      <div className="flex justify-end gap-2 pt-1">
        <button
          type="button"
          onClick={onClose}
          disabled={deleting}
          className="px-4 py-2 text-xs font-semibold text-slate-600 dark:text-slate-300 hover:text-slate-800 dark:hover:text-slate-100 rounded-xl cursor-pointer"
        >
          取消
        </button>
        <button
          type="button"
          onClick={onConfirm}
          disabled={deleting}
          className="px-4 py-2 bg-rose-600 hover:bg-rose-700 disabled:opacity-50 text-white text-xs font-bold rounded-xl flex items-center gap-1.5 cursor-pointer"
        >
          <Trash2 className="w-3.5 h-3.5" />
          {deleting ? '删除中...' : '确认删除'}
        </button>
      </div>
    </div>
  </div>
);

/** 单条删除收藏确认（卡片右键菜单【删除】） */
export const BrowserSingleDeleteModal: React.FC<{
  item: ScrapedItem;
  deleting: boolean;
  onClose: () => void;
  onConfirm: () => void;
}> = ({ item, deleting, onClose, onConfirm }) => (
  <div
    className="fixed inset-0 z-[70] bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 anim-backdrop-enter"
    onClick={() => !deleting && onClose()}
  >
    <div
      onClick={(e) => e.stopPropagation()}
      className="anim-modal-enter bg-white dark:bg-[#161B26] w-full max-w-sm rounded-[28px] p-6 shadow-2xl border border-slate-100 dark:border-slate-800 space-y-4"
    >
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-2xl bg-rose-50 dark:bg-rose-950 text-rose-600 dark:text-rose-400 flex items-center justify-center shrink-0">
          <AlertTriangle className="w-5 h-5" />
        </div>
        <h3 className="text-base font-bold text-slate-900 dark:text-white">删除收藏</h3>
      </div>
      <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
        确定删除收藏「
        <strong className="text-slate-900 dark:text-white break-all line-clamp-2">{item.title}</strong>
        」吗？删除后将从收藏列表移除（不可恢复），内容元数据保留。
      </p>
      <div className="flex justify-end gap-2 pt-1">
        <button
          type="button"
          onClick={onClose}
          disabled={deleting}
          className="px-4 py-2 text-xs font-semibold text-slate-600 dark:text-slate-300 hover:text-slate-800 dark:hover:text-slate-100 rounded-xl cursor-pointer"
        >
          取消
        </button>
        <button
          type="button"
          onClick={onConfirm}
          disabled={deleting}
          className="px-4 py-2 bg-rose-600 hover:bg-rose-700 disabled:opacity-50 text-white text-xs font-bold rounded-xl flex items-center gap-1.5 cursor-pointer"
        >
          <Trash2 className="w-3.5 h-3.5" />
          {deleting ? '删除中...' : '确认删除'}
        </button>
      </div>
    </div>
  </div>
);
