import React, { useRef } from 'react';
import { AlertTriangle, Trash2, X, Plus } from 'lucide-react';
import { useDismiss } from '../../hooks/useDismiss';
import * as api from '../../api';

/** 标签右键菜单（自 DataBrowserView 抽离）：点击外部/滚动自动关闭 */
export const BrowserTagContextMenu: React.FC<{
  ctxMenu: { x: number; y: number; tag: string };
  onClose: () => void;
  onDeleteTag: (tag: string) => void;
}> = ({ ctxMenu, onClose, onDeleteTag }) => {
  // 浮层内部点击由按钮 onClick 自行处理
  const tagMenuRef = useRef<HTMLDivElement>(null);
  useDismiss(onClose, true, tagMenuRef);

  return (
    <div
      ref={tagMenuRef}
      className="fixed z-[60] py-1 rounded-xl bg-white dark:bg-[#161B26] border border-slate-200 dark:border-slate-700 shadow-lg overflow-hidden anim-modal-enter"
      style={{ left: Math.min(ctxMenu.x, window.innerWidth - 140), top: ctxMenu.y }}
      onClick={(e) => e.stopPropagation()}
    >
      <button
        type="button"
        onClick={() => onDeleteTag(ctxMenu.tag)}
        className="w-full px-3.5 py-2 text-left text-xs font-semibold text-rose-600 hover:bg-rose-50 flex items-center gap-2 cursor-pointer"
      >
        <Trash2 className="w-3.5 h-3.5" />
        删除标签「{ctxMenu.tag}」
      </button>
    </div>
  );
};

/** 删除标签确认（AlertDialog + checkbox，默认不勾选） */
export const BrowserTagDeleteModal: React.FC<{
  confirm: { tag: string; usage: number };
  alsoContents: boolean;
  onAlsoContentsChange: (v: boolean) => void;
  deleting: boolean;
  onClose: () => void;
  onConfirm: () => void;
}> = ({ confirm, alsoContents, onAlsoContentsChange, deleting, onClose, onConfirm }) => (
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
        <h3 className="text-base font-bold text-slate-900 dark:text-white">删除标签</h3>
      </div>
      <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
        将从
        {confirm.usage >= 0 ? (
          <>
            <strong className="text-slate-900 dark:text-white">{confirm.usage}</strong> 条内容中
          </>
        ) : ''}{' '}
        移除标签 <span className="font-bold text-violet-600">#{confirm.tag}</span>
        （含各分组内的该标签）。
      </p>
      <label className="flex items-start gap-2.5 p-3 rounded-2xl bg-rose-50/60 border border-rose-100 cursor-pointer">
        <input
          type="checkbox"
          checked={alsoContents}
          onChange={(e) => onAlsoContentsChange(e.target.checked)}
          className="mt-0.5 w-4 h-4 rounded accent-rose-600 cursor-pointer"
        />
        <span className="text-xs text-slate-700 dark:text-slate-300">
          <strong className="text-rose-600 dark:text-rose-400">一并删除这些收藏内容</strong>
          <span className="block text-[11px] text-slate-400 mt-0.5">
            含该标签的收藏将全部从收藏库移除（不可恢复），内容元数据保留
          </span>
        </span>
      </label>
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
          {deleting ? '删除中...' : alsoContents ? '删除标签与收藏' : '删除标签'}
        </button>
      </div>
    </div>
  </div>
);

/** 新建分组弹窗（可选归入「其他」组标签） */
export const BrowserGroupCreateModal: React.FC<{
  groups: api.TagGroupRow[];
  name: string;
  onNameChange: (v: string) => void;
  pickedTags: string[];
  onTogglePickedTag: (t: string) => void;
  saving: boolean;
  onClose: () => void;
  onSubmit: () => void;
}> = ({ groups, name, onNameChange, pickedTags, onTogglePickedTag, saving, onClose, onSubmit }) => (
  <div
    className="fixed inset-0 z-[70] bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 anim-backdrop-enter"
    onClick={() => !saving && onClose()}
  >
    <div
      onClick={(e) => e.stopPropagation()}
      className="anim-modal-enter bg-white dark:bg-[#161B26] w-full max-w-sm rounded-[28px] shadow-2xl border border-slate-100 dark:border-slate-800 overflow-hidden"
    >
      <div className="p-5 bg-slate-50 dark:bg-slate-800 border-b border-slate-100 dark:border-slate-800">
        <h3 className="text-base font-bold text-slate-900 dark:text-white">新建标签分组</h3>
        <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
          创建后可在分组内积累标签，打标标签池同步生效
        </p>
      </div>
      <div className="p-5 space-y-4">
        <input
          autoFocus
          type="text"
          value={name}
          onChange={(e) => onNameChange(e.target.value)}
          placeholder="分组名称，如：兴趣爱好"
          className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 text-sm dark:bg-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-violet-600"
        />
        {(() => {
          const otherGroup = groups.find((g) => g.group === '其他');
          const otherTags = otherGroup?.tags || [];
          if (otherTags.length === 0) {
            return (
              <p className="text-[11px] text-slate-400">
                当前没有未分组标签；创建空分组后，手动打标或模型新增的标签如需归组可编辑分组。
              </p>
            );
          }
          return (
            <div>
              <span className="text-xs font-bold text-slate-600 dark:text-slate-400 block mb-2">
                归入「其他」组的标签（可选）
              </span>
              <div className="flex flex-wrap gap-1.5 max-h-40 overflow-y-auto p-1">
                {otherTags.map((t) => {
                  const on = pickedTags.includes(t);
                  return (
                    <button
                      key={t}
                      type="button"
                      onClick={() => onTogglePickedTag(t)}
                      className={`px-2 py-1 rounded-lg text-[11px] font-medium border transition-all cursor-pointer active:scale-95 ${
                        on
                          ? 'bg-violet-600 text-white border-violet-600'
                          : 'bg-violet-50/60 dark:bg-violet-950 text-violet-600 dark:text-violet-400 border-violet-100 dark:border-violet-900 hover:bg-violet-100 dark:hover:bg-violet-900'
                      }`}
                    >
                      #{t}
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })()}
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
            onClick={onSubmit}
            disabled={saving || !name.trim()}
            className="px-4 py-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white text-xs font-bold rounded-xl flex items-center gap-1.5 cursor-pointer"
          >
            <Plus className="w-3.5 h-3.5" />
            {saving ? '创建中...' : '创建分组'}
          </button>
        </div>
      </div>
    </div>
  </div>
);
