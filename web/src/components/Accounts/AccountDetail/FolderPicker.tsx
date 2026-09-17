import React, { useState } from 'react';
import { Account, BilibiliFolder } from '../../../types';
import { deleteBilibiliFolder, editBilibiliFolder } from '../../../api';
import { AlertTriangle, FolderHeart, MoreVertical, Pencil, RefreshCw, Trash2 } from 'lucide-react';

interface FolderPickerProps {
  account: Account;
  selectedMediaId: string;
  onSelect: (mediaId: string) => void;
  /** 收藏夹增删改成功后通知父级刷新账号（folders 来自 account.extra） */
  onFoldersChanged?: () => void;
}

/**
 * 收藏夹 Tab 面板：Tab 内展示名下收藏夹列表（点击卡片设为抓取目标），
 * 自建收藏夹卡片右上角 dots 菜单可编辑 / 删除（调 Bilibili folder API），
 * 无收藏夹时仍渲染 Tab 头 + 空占位。
 */
export const FolderPicker: React.FC<FolderPickerProps> = ({
  account,
  selectedMediaId,
  onSelect,
  onFoldersChanged,
}) => {
  const folders = account.folders || [];

  // dots 菜单与编辑/删除弹窗状态
  const [menuFor, setMenuFor] = useState<string | null>(null);
  const [editTarget, setEditTarget] = useState<BilibiliFolder | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<BilibiliFolder | null>(null);
  const [editForm, setEditForm] = useState({ title: '', intro: '', privacy: '0' });
  const [opBusy, setOpBusy] = useState(false);
  const [opError, setOpError] = useState('');

  const openEdit = (f: BilibiliFolder) => {
    setMenuFor(null);
    setEditTarget(f);
    setEditForm({ title: f.name, intro: f.intro || '', privacy: '0' });
    setOpError('');
  };

  const submitEdit = async () => {
    if (!editTarget) return;
    const title = editForm.title.trim();
    if (!title) {
      setOpError('收藏夹标题不能为空');
      return;
    }
    setOpBusy(true);
    setOpError('');
    try {
      await editBilibiliFolder(account.id, {
        media_id: editTarget.mediaId,
        title,
        intro: editForm.intro.trim(),
        privacy: Number(editForm.privacy),
      });
      setEditTarget(null);
      onFoldersChanged?.();
    } catch (e) {
      setOpError(e instanceof Error ? e.message : String(e));
    } finally {
      setOpBusy(false);
    }
  };

  const submitDelete = async () => {
    if (!deleteTarget) return;
    setOpBusy(true);
    setOpError('');
    try {
      await deleteBilibiliFolder(account.id, deleteTarget.mediaId);
      setDeleteTarget(null);
      onFoldersChanged?.();
    } catch (e) {
      setOpError(e instanceof Error ? e.message : String(e));
    } finally {
      setOpBusy(false);
    }
  };

  return (
    <div className="bg-white rounded-[28px] border border-slate-200/80 shadow-2xs overflow-hidden">
      {/* Tab Header */}
      <div className="flex items-center justify-between border-b border-slate-100 px-6 pt-4 pb-1">
        <div className="flex items-center gap-4">
          <span className="pb-3 text-sm font-bold border-b-2 border-slate-900 text-slate-900 flex items-center gap-1.5">
            <FolderHeart className="w-4 h-4 text-indigo-600" />
            收藏夹 ({folders.length})
          </span>
        </div>
        <span className="text-[11px] text-slate-400 hidden sm:inline-block">
          {folders.length > 0 ? '点击卡片设为抓取目标' : '自动同步自平台接口'}
        </span>
      </div>

      {/* Tab Content：收藏夹列表网格，或空占位 */}
      <div className="p-6">
        {folders.length > 0 ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
            {folders.map((f) => {
              const isSelected = selectedMediaId === f.mediaId;
              return (
                <div key={f.id} className="relative">
                  <button
                    type="button"
                    onClick={() => onSelect(f.mediaId)}
                    className={`w-full p-3 rounded-xl border text-left transition-all ${
                      isSelected
                        ? 'border-indigo-600 bg-indigo-50/50 ring-2 ring-indigo-500/20 shadow-2xs'
                        : 'border-slate-200 hover:border-slate-300 hover:bg-slate-50'
                    } ${!f.isDefault ? 'pr-7' : ''}`}
                  >
                    <div className="flex items-center justify-between text-xs font-bold text-slate-900 mb-1">
                      <span className="truncate">{f.name}</span>
                      {f.isDefault && (
                        <span className="text-[9px] bg-slate-200 text-slate-700 px-1 rounded">默认</span>
                      )}
                    </div>
                    <div className="text-xs text-slate-500 flex items-center justify-between">
                      <span>{f.count} 件</span>
                      <span className="font-mono text-[10px] text-slate-400">ID:{f.mediaId}</span>
                    </div>
                  </button>

                  {/* 自建收藏夹：右上角 dots 菜单（默认收藏夹不可编辑/删除） */}
                  {!f.isDefault && (
                    <button
                      type="button"
                      title="收藏夹操作"
                      onClick={(e) => {
                        e.stopPropagation();
                        setMenuFor(menuFor === f.mediaId ? null : f.mediaId);
                      }}
                      className={`absolute top-1.5 right-1.5 p-1 rounded-md transition-colors ${
                        menuFor === f.mediaId
                          ? 'bg-slate-100 text-slate-700'
                          : 'text-slate-300 hover:text-slate-600 hover:bg-slate-100'
                      }`}
                    >
                      <MoreVertical className="w-3.5 h-3.5" />
                    </button>
                  )}
                  {menuFor === f.mediaId && (
                    <>
                      {/* 点击菜单外任意处关闭 */}
                      <div className="fixed inset-0 z-10" onClick={() => setMenuFor(null)} />
                      <div className="absolute top-8 right-1 z-20 w-28 py-1 bg-white rounded-lg border border-slate-200 shadow-lg">
                        <button
                          type="button"
                          onClick={() => openEdit(f)}
                          className="w-full px-3 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-50 flex items-center gap-1.5"
                        >
                          <Pencil className="w-3 h-3" />
                          编辑信息
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setMenuFor(null);
                            setDeleteTarget(f);
                            setOpError('');
                          }}
                          className="w-full px-3 py-1.5 text-left text-xs text-rose-600 hover:bg-rose-50 flex items-center gap-1.5"
                        >
                          <Trash2 className="w-3 h-3" />
                          删除收藏夹
                        </button>
                      </div>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50/60 h-32 flex flex-col items-center justify-center text-center gap-1.5">
            <FolderHeart className="w-5 h-5 text-slate-300" />
            <span className="text-[11px] text-slate-400">暂无收藏夹，平台同步后将显示在此</span>
          </div>
        )}
      </div>

      {/* 编辑收藏夹弹窗 */}
      {editTarget && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="anim-modal-enter bg-white w-full max-w-sm rounded-2xl p-5 shadow-2xl border border-slate-100">
            <h3 className="text-sm font-bold text-slate-900 mb-4 flex items-center gap-1.5">
              <Pencil className="w-4 h-4 text-slate-400" />
              编辑收藏夹
            </h3>
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1.5">标题 <span className="text-rose-500">*</span></label>
                <input
                  type="text"
                  value={editForm.title}
                  onChange={(e) => setEditForm((f) => ({ ...f, title: e.target.value }))}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1.5">简介</label>
                <textarea
                  value={editForm.intro}
                  onChange={(e) => setEditForm((f) => ({ ...f, intro: e.target.value }))}
                  rows={3}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1.5">隐私</label>
                <select
                  value={editForm.privacy}
                  onChange={(e) => setEditForm((f) => ({ ...f, privacy: e.target.value }))}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-slate-900"
                >
                  <option value="0">公开</option>
                  <option value="1">私密</option>
                </select>
              </div>
              {opError && (
                <p className="text-[11px] text-rose-600 bg-rose-50 border border-rose-200 p-2 rounded-lg">{opError}</p>
              )}
            </div>
            <div className="flex justify-end gap-2 pt-4">
              <button
                type="button"
                disabled={opBusy}
                onClick={() => setEditTarget(null)}
                className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-800 rounded-xl disabled:opacity-50"
              >
                取消
              </button>
              <button
                type="button"
                disabled={opBusy || !editForm.title.trim()}
                onClick={submitEdit}
                className="px-5 py-2 text-xs font-bold text-white bg-slate-900 hover:bg-slate-800 rounded-xl shadow-xs disabled:opacity-50 inline-flex items-center gap-1.5"
              >
                {opBusy && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                保存
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 删除收藏夹确认弹窗 */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="anim-modal-enter bg-white w-full max-w-sm rounded-2xl p-5 shadow-2xl border border-slate-100">
            <h3 className="text-sm font-bold text-rose-700 mb-2 flex items-center gap-1.5">
              <AlertTriangle className="w-4 h-4" />
              删除收藏夹
            </h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              将删除收藏夹「{deleteTarget.name}」及其中的 {deleteTarget.count} 件收藏，操作不可恢复，确定继续？
            </p>
            {opError && (
              <p className="mt-3 text-[11px] text-rose-600 bg-rose-50 border border-rose-200 p-2 rounded-lg">{opError}</p>
            )}
            <div className="flex justify-end gap-2 pt-4">
              <button
                type="button"
                disabled={opBusy}
                onClick={() => setDeleteTarget(null)}
                className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-800 rounded-xl disabled:opacity-50"
              >
                取消
              </button>
              <button
                type="button"
                disabled={opBusy}
                onClick={submitDelete}
                className="px-5 py-2 text-xs font-bold text-white bg-rose-600 hover:bg-rose-700 rounded-xl shadow-xs disabled:opacity-50 inline-flex items-center gap-1.5"
              >
                {opBusy && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                确认删除
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
