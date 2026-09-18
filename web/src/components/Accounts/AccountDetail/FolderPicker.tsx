import React, { useState } from 'react';
import { Account, BilibiliFolder } from '../../../types';
import { deleteBilibiliFolder, editBilibiliFolder, syncBilibiliFolders } from '../../../api';
import {
  AlertTriangle, CheckSquare, FolderHeart, ListChecks, MoreVertical, Pencil, RefreshCw, Square, Trash2, UserPlus,
} from 'lucide-react';
import { FollowingList } from './FollowingList';

interface FolderPickerProps {
  account: Account;
  selectedMediaId: string;
  onSelect: (mediaId: string) => void;
  /** 收藏夹增删改成功后通知父级刷新账号（folders 来自 account.extra） */
  onFoldersChanged?: () => void;
}

// 批量删除的请求间隔（防风控）
const DELETE_INTERVAL_MS = 3000;

/**
 * 收藏夹 Tab 面板：Tab 内展示名下收藏夹列表（点击卡片设为抓取目标），
 * 自建收藏夹卡片右上角 dots 菜单可编辑 / 删除（调 Bilibili folder API）；
 * 头部右侧多选开关可勾选多个收藏夹批量删除，无收藏夹时仍渲染 Tab 头 + 空占位。
 * douyin 账号另有「关注列表」Tab（拉取关注博主并添加特别关注），与本卡片共用 tabs。
 */
export const FolderPicker: React.FC<FolderPickerProps> = ({
  account,
  selectedMediaId,
  onSelect,
  onFoldersChanged,
}) => {
  const folders = account.folders || [];

  // 卡片内 tabs：收藏夹 / 关注列表（关注列表目前仅 douyin 提供）
  const [listTab, setListTab] = useState<'folders' | 'following'>('folders');

  // dots 菜单与编辑/删除弹窗状态
  const [menuFor, setMenuFor] = useState<string | null>(null);
  const [editTarget, setEditTarget] = useState<BilibiliFolder | null>(null);
  const [deleteTargets, setDeleteTargets] = useState<BilibiliFolder[] | null>(null);
  const [deleteProgress, setDeleteProgress] = useState<{ done: number; total: number; current: string } | null>(null);
  const [editForm, setEditForm] = useState({ title: '', intro: '', privacy: '0' });
  const [opBusy, setOpBusy] = useState(false);
  const [opError, setOpError] = useState('');
  const [syncing, setSyncing] = useState(false);

  // 走 API 拉取最新收藏夹列表（Bilibili 专属按钮）
  const syncFolders = async () => {
    setSyncing(true);
    try {
      await syncBilibiliFolders(account.id);
      onFoldersChanged?.();
    } catch (e) {
      setOpError(e instanceof Error ? e.message : String(e));
    } finally {
      setSyncing(false);
    }
  };

  // 多选模式与勾选集合（默认收藏夹不可删，不参与勾选）
  const [multiSelect, setMultiSelect] = useState(false);
  const [checked, setChecked] = useState<Set<string>>(new Set());

  const toggleMultiSelect = () => {
    setMultiSelect((prev) => !prev);
    setChecked(new Set());
    setMenuFor(null);
  };

  const toggleChecked = (mediaId: string) => {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(mediaId)) {
        next.delete(mediaId);
      } else {
        next.add(mediaId);
      }
      return next;
    });
  };

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
    if (!deleteTargets?.length) return;
    setOpBusy(true);
    setOpError('');
    let deleted = 0;
    const errors: { folder: BilibiliFolder; message: string }[] = [];
    for (let i = 0; i < deleteTargets.length; i++) {
      const f = deleteTargets[i];
      setDeleteProgress({ done: i, total: deleteTargets.length, current: f.name });
      try {
        await deleteBilibiliFolder(account.id, f.mediaId);
        deleted++;
      } catch (e) {
        errors.push({ folder: f, message: e instanceof Error ? e.message : String(e) });
      }
      // 非最后一个：间隔防风控（失败的重试也受同样间隔约束）
      if (i < deleteTargets.length - 1) {
        await new Promise((resolve) => setTimeout(resolve, DELETE_INTERVAL_MS));
      }
    }
    setDeleteProgress(null);
    setOpBusy(false);
    if (deleted > 0) {
      onFoldersChanged?.();
      setChecked(new Set());
    }
    if (errors.length) {
      // 部分失败：弹窗保留失败清单与剩余目标，方便重试
      setOpError(errors.map((e) => `「${e.folder.name}」：${e.message}`).join('；'));
      setDeleteTargets((prev) =>
        prev ? prev.filter((f) => !errors.some((e) => e.folder.mediaId === f.mediaId)) : prev
      );
    } else {
      setDeleteTargets(null);
    }
  };

  return (
    <div className="bg-white dark:bg-[#161B26] rounded-[28px] border border-slate-200/80 dark:border-slate-800 shadow-2xs overflow-hidden">
      {/* Tab Header：左=tabs（收藏夹/关注列表），右=多选开关 + 批量删除按钮（仅收藏夹 tab） */}
      <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 px-6 pt-4 pb-1">
        <div className="flex items-center gap-4">
          <button
            type="button"
            onClick={() => setListTab('folders')}
            className={`pb-3 text-sm font-bold border-b-2 transition-colors flex items-center gap-1.5 cursor-pointer ${
              listTab === 'folders'
                ? 'border-slate-900 dark:border-slate-100 text-slate-900 dark:text-white'
                : 'border-transparent text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200'
            }`}
          >
            <FolderHeart className="w-4 h-4 text-indigo-600" />
            收藏夹 ({folders.length})
          </button>
          {account.platform === 'douyin' && (
            <button
              type="button"
              onClick={() => setListTab('following')}
              className={`pb-3 text-sm font-bold border-b-2 transition-colors flex items-center gap-1.5 cursor-pointer ${
                listTab === 'following'
                  ? 'border-slate-900 dark:border-slate-100 text-slate-900 dark:text-white'
                  : 'border-transparent text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200'
              }`}
            >
              <UserPlus className="w-4 h-4 text-sky-500" />
              关注列表
            </button>
          )}
        </div>
        <div className="flex items-center gap-2 pb-2">
          {listTab === 'folders' && folders.length > 0 && (
            <span className="text-[11px] text-slate-400 hidden sm:inline-block">
              {multiSelect ? `已选 ${checked.size} 个` : '点击卡片设为抓取目标'}
            </span>
          )}
          {listTab === 'folders' && account.platform === 'bilibili' && (
            <button
              type="button"
              title={syncing ? '正在同步…' : '从 B 站刷新收藏夹列表'}
              disabled={syncing}
              onClick={syncFolders}
              className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors disabled:opacity-40"
            >
              <RefreshCw className={`w-4 h-4 ${syncing ? 'animate-spin' : ''}`} />
            </button>
          )}
          {listTab === 'folders' && folders.length > 0 && (
            <button
              type="button"
              title={multiSelect ? '退出多选' : '多选管理收藏夹'}
              onClick={toggleMultiSelect}
              className={`p-1.5 rounded-lg transition-colors ${
                multiSelect
                  ? 'bg-indigo-50 dark:bg-indigo-950 text-indigo-600 dark:text-indigo-400 ring-1 ring-indigo-200 dark:ring-indigo-800'
                  : 'text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'
              }`}
            >
              <ListChecks className="w-4 h-4" />
            </button>
          )}
          {listTab === 'folders' && multiSelect && (
            <button
              type="button"
              title={checked.size ? `删除选中的 ${checked.size} 个收藏夹` : '先勾选要删除的收藏夹'}
              disabled={!checked.size || opBusy}
              onClick={() => {
                setOpError('');
                setDeleteTargets(folders.filter((f) => checked.has(f.mediaId)));
              }}
              className="p-1.5 rounded-lg text-rose-500 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950 transition-colors disabled:opacity-40 disabled:hover:bg-transparent"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Tab Content：关注列表（douyin）/ 收藏夹列表网格，或空占位 */}
      <div className="p-6">
        {listTab === 'following' ? (
          <FollowingList account={account} />
        ) : (
        <>
        {opError && !editTarget && !deleteTargets && (
          <p className="mb-2.5 text-[11px] text-rose-600 dark:text-rose-400 bg-rose-50 dark:bg-rose-950 border border-rose-200 dark:border-rose-800 p-2 rounded-lg">
            {opError}
          </p>
        )}
        {folders.length > 0 ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-2.5">
            {folders.map((f) => {
              const isSelected = selectedMediaId === f.mediaId;
              const isChecked = checked.has(f.mediaId);
              const checkable = multiSelect && !f.isDefault;
              return (
                <div key={f.id} className="relative">
                  <button
                    type="button"
                    onClick={() => {
                      if (multiSelect) {
                        if (checkable) toggleChecked(f.mediaId);
                        return; // 默认夹多选模式不可勾选；多选模式不切换抓取目标
                      }
                      // 再次点击已选中的卡片取消选择（清空抓取目标）
                      onSelect(isSelected ? '' : f.mediaId);
                    }}
                    className={`w-full p-3 rounded-xl border text-left transition-all ${
                      isChecked
                        ? 'border-indigo-600 bg-indigo-50/50 dark:bg-indigo-950/50 ring-2 ring-indigo-500/20 shadow-2xs'
                        : isSelected && !multiSelect
                          ? 'border-indigo-600 bg-indigo-50/50 dark:bg-indigo-950/50 ring-2 ring-indigo-500/20 shadow-2xs'
                          : multiSelect && f.isDefault
                            ? 'border-slate-100 dark:border-slate-700 bg-slate-50/40 dark:bg-slate-800/40 cursor-not-allowed opacity-60'
                            : 'border-slate-200 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-800'
                    } ${!f.isDefault && !multiSelect ? 'pr-7' : ''} ${multiSelect ? 'pl-8' : ''}`}
                  >
                    {multiSelect && (
                      <span className={`absolute left-2 top-2.5 ${f.isDefault ? 'text-slate-300' : isChecked ? 'text-indigo-600' : 'text-slate-300'}`}>
                        {isChecked ? <CheckSquare className="w-4 h-4" /> : <Square className="w-4 h-4" />}
                      </span>
                    )}
                    <div className="flex items-center justify-between text-xs font-bold text-slate-900 dark:text-white mb-1">
                      <span className="truncate">{f.name}</span>
                      {f.isDefault && (
                        <span className="text-[9px] bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-200 px-1 rounded">默认</span>
                      )}
                    </div>
                    <div className="text-xs text-slate-500 dark:text-slate-400 flex items-center justify-between">
                      <span>{f.count} 件</span>
                      <span className="font-mono text-[10px] text-slate-400">ID:{f.mediaId}</span>
                    </div>
                  </button>

                  {/* 自建收藏夹：右上角 dots 菜单（默认收藏夹不可编辑/删除；多选模式下隐藏） */}
                  {!f.isDefault && !multiSelect && (
                    <button
                      type="button"
                      title="收藏夹操作"
                      onClick={(e) => {
                        e.stopPropagation();
                        setMenuFor(menuFor === f.mediaId ? null : f.mediaId);
                      }}
                      className={`absolute top-1.5 right-1.5 p-1 rounded-md transition-colors ${
                        menuFor === f.mediaId
                          ? 'bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200'
                          : 'text-slate-300 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'
                      }`}
                    >
                      <MoreVertical className="w-3.5 h-3.5" />
                    </button>
                  )}
                  {menuFor === f.mediaId && !multiSelect && (
                    <>
                      {/* 点击菜单外任意处关闭 */}
                      <div className="fixed inset-0 z-10" onClick={() => setMenuFor(null)} />
                      <div className="absolute top-8 right-1 z-20 w-28 py-1 bg-white dark:bg-[#161B26] rounded-lg border border-slate-200 dark:border-slate-700 shadow-lg">
                        <button
                          type="button"
                          onClick={() => openEdit(f)}
                          className="w-full px-3 py-1.5 text-left text-xs text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800 flex items-center gap-1.5"
                        >
                          <Pencil className="w-3 h-3" />
                          编辑信息
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setMenuFor(null);
                            setOpError('');
                            setDeleteTargets([f]);
                          }}
                          className="w-full px-3 py-1.5 text-left text-xs text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950 flex items-center gap-1.5"
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
          <div className="rounded-2xl border border-dashed border-slate-200 dark:border-slate-700 bg-slate-50/60 dark:bg-slate-800/40 h-32 flex flex-col items-center justify-center text-center gap-1.5">
            <FolderHeart className="w-5 h-5 text-slate-300" />
            <span className="text-[11px] text-slate-400">暂无收藏夹，平台同步后将显示在此</span>
          </div>
        )}
        </>
        )}
      </div>

      {/* 编辑收藏夹弹窗 */}
      {editTarget && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="anim-modal-enter bg-white dark:bg-[#161B26] w-full max-w-sm rounded-2xl p-5 shadow-2xl border border-slate-100 dark:border-slate-800">
            <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-4 flex items-center gap-1.5">
              <Pencil className="w-4 h-4 text-slate-400" />
              编辑收藏夹
            </h3>
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5">标题 <span className="text-rose-500">*</span></label>
                <input
                  type="text"
                  value={editForm.title}
                  onChange={(e) => setEditForm((f) => ({ ...f, title: e.target.value }))}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-sm bg-transparent dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-slate-900"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5">简介</label>
                <textarea
                  value={editForm.intro}
                  onChange={(e) => setEditForm((f) => ({ ...f, intro: e.target.value }))}
                  rows={3}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-sm bg-transparent dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-slate-900"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5">隐私</label>
                <select
                  value={editForm.privacy}
                  onChange={(e) => setEditForm((f) => ({ ...f, privacy: e.target.value }))}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-sm bg-white dark:bg-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-slate-900"
                >
                  <option value="0">公开</option>
                  <option value="1">私密</option>
                </select>
              </div>
              {opError && (
                <p className="text-[11px] text-rose-600 dark:text-rose-400 bg-rose-50 dark:bg-rose-950 border border-rose-200 dark:border-rose-800 p-2 rounded-lg">{opError}</p>
              )}
            </div>
            <div className="flex justify-end gap-2 pt-4">
              <button
                type="button"
                disabled={opBusy}
                onClick={() => setEditTarget(null)}
                className="px-4 py-2 text-xs font-semibold text-slate-600 dark:text-slate-300 hover:text-slate-800 dark:hover:text-slate-100 rounded-xl disabled:opacity-50"
              >
                取消
              </button>
              <button
                type="button"
                disabled={opBusy || !editForm.title.trim()}
                onClick={submitEdit}
                className="px-5 py-2 text-xs font-bold text-white bg-slate-900 hover:bg-slate-800 dark:bg-slate-700 dark:hover:bg-slate-600 rounded-xl shadow-xs disabled:opacity-50 inline-flex items-center gap-1.5"
              >
                {opBusy && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                保存
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 删除收藏夹确认弹窗（单个 dots 菜单 / 多选批量共用） */}
      {deleteTargets && deleteTargets.length > 0 && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="anim-modal-enter bg-white dark:bg-[#161B26] w-full max-w-sm rounded-2xl p-5 shadow-2xl border border-slate-100 dark:border-slate-800">
            <h3 className="text-sm font-bold text-rose-700 dark:text-rose-400 mb-2 flex items-center gap-1.5">
              <AlertTriangle className="w-4 h-4" />
              {deleteTargets.length === 1 ? '删除收藏夹' : `批量删除 ${deleteTargets.length} 个收藏夹`}
            </h3>
            {deleteTargets.length === 1 ? (
              <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
                将删除收藏夹「{deleteTargets[0].name}」及其中的 {deleteTargets[0].count} 件收藏，操作不可恢复，确定继续？
              </p>
            ) : (
              <div className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
                <p>
                  将删除 {deleteTargets.length} 个收藏夹（共{' '}
                  {deleteTargets.reduce((sum, f) => sum + f.count, 0)} 件收藏），操作不可恢复，确定继续？
                </p>
                <p className="mt-1.5 text-[11px] text-slate-400 line-clamp-2">
                  {deleteTargets.map((f) => f.name).join('、')}
                </p>
              </div>
            )}
            {deleteProgress && (
              <div className="mt-3 space-y-1.5">
                <div className="flex items-center justify-between gap-2 text-[11px] text-slate-500 dark:text-slate-400">
                  <span className="truncate">正在删除「{deleteProgress.current}」，每个间隔 3 秒防风控…</span>
                  <span className="font-mono shrink-0">{deleteProgress.done + 1}/{deleteProgress.total}</span>
                </div>
                <div className="h-1.5 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-rose-500 rounded-full transition-all duration-300"
                    style={{ width: `${((deleteProgress.done + 1) / deleteProgress.total) * 100}%` }}
                  />
                </div>
              </div>
            )}
            {opError && (
              <p className="mt-3 text-[11px] text-rose-600 dark:text-rose-400 bg-rose-50 dark:bg-rose-950 border border-rose-200 dark:border-rose-800 p-2 rounded-lg whitespace-pre-wrap">{opError}</p>
            )}
            <div className="flex justify-end gap-2 pt-4">
              <button
                type="button"
                disabled={opBusy}
                onClick={() => setDeleteTargets(null)}
                className="px-4 py-2 text-xs font-semibold text-slate-600 dark:text-slate-300 hover:text-slate-800 dark:hover:text-slate-100 rounded-xl disabled:opacity-50"
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
                {opBusy ? '删除中...' : '确认删除'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
