import React from 'react';
import { LayoutGrid, List, Loader2, Sparkles, X, CheckSquare, Download, Trash2, ArrowUp, ArrowDown } from 'lucide-react';

/** 列表排序字段：default 按抓取入库时间，collected 收藏时间，duration 时长 */
export type BrowserSortBy = 'default' | 'collected' | 'duration';

/** 右列头部：标题 + 排序/视图切换/多选/一键打标（移动端页面滚动时吸顶），自 DataBrowserView 抽离 */
export const BrowserToolbar: React.FC<{
  listLoading: boolean;
  viewMode: 'grid' | 'list';
  onViewModeChange: (mode: 'grid' | 'list') => void;
  selectionMode: boolean;
  onEnterSelectionMode: () => void;
  onExitSelectionMode: () => void;
  totalCount: number;
  selectedCount: number;
  agentsAvailable: boolean;
  onOpenTagModal: () => void;
  sortBy: BrowserSortBy;
  onSortByChange: (by: BrowserSortBy) => void;
  sortAsc: boolean;
  onToggleSortOrder: () => void;
}> = ({
  listLoading,
  viewMode,
  onViewModeChange,
  selectionMode,
  onEnterSelectionMode,
  onExitSelectionMode,
  totalCount,
  selectedCount,
  agentsAvailable,
  onOpenTagModal,
  sortBy,
  onSortByChange,
  sortAsc,
  onToggleSortOrder,
}) => (
  <div className="sticky top-0 z-20 bg-[#F8FAFC] dark:bg-[#0D1117] flex flex-col sm:flex-row sm:items-center justify-between gap-4">
    <div>
      <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-2">
        数据浏览
        {listLoading && <Loader2 className="w-4 h-4 text-violet-500 animate-spin" />}
      </h2>
    </div>

    {/* View mode toggle: List vs Grid + 一键打标 + 多选 */}
    <div className="flex flex-wrap items-center gap-2.5 self-start sm:self-auto">
      {selectionMode ? (
        <button
          type="button"
          onClick={onExitSelectionMode}
          className="px-4 py-2 rounded-2xl bg-slate-900 hover:bg-slate-800 dark:bg-slate-700 dark:hover:bg-slate-600 text-white text-xs font-bold shadow-sm inline-flex items-center gap-1.5 transition-all active:scale-95 cursor-pointer"
        >
          <X className="w-3.5 h-3.5" />
          退出多选
        </button>
      ) : (
        <button
          type="button"
          onClick={onEnterSelectionMode}
          disabled={totalCount === 0}
          className="px-4 py-2 rounded-2xl bg-white dark:bg-slate-800 hover:bg-slate-100 dark:hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 text-xs font-bold shadow-sm inline-flex items-center gap-1.5 transition-all active:scale-95 cursor-pointer"
          title="进入多选模式，可勾选多条收藏批量删除"
        >
          <CheckSquare className="w-3.5 h-3.5" />
          多选
        </button>
      )}
      <button
        type="button"
        onClick={onOpenTagModal}
        disabled={!agentsAvailable}
        className="px-4 py-2 rounded-2xl bg-violet-600 hover:bg-violet-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-bold shadow-sm inline-flex items-center gap-1.5 transition-all active:scale-95 cursor-pointer"
        title={agentsAvailable ? '对未打标的收藏内容执行一次性 AI 打标' : '请先在设置页创建 AI Agent 配置'}
      >
        <Sparkles className="w-3.5 h-3.5" />
        一键打标
      </button>
      {/* 排序：字段 + 正反序 */}
      <div className="bg-white dark:bg-slate-800 p-1 rounded-2xl border border-slate-200 dark:border-slate-700 flex items-center gap-1 shadow-2xs">
        <select
          value={sortBy}
          onChange={(e) => onSortByChange(e.target.value as BrowserSortBy)}
          title="列表排序字段（收藏时间/时长为空值的条目恒排末尾）"
          className="px-2 py-1.5 rounded-xl text-xs font-semibold bg-transparent text-slate-700 dark:text-slate-200 outline-none cursor-pointer"
        >
          <option value="default">默认排序</option>
          <option value="collected">收藏时间</option>
          <option value="duration">时长</option>
        </select>
        <button
          type="button"
          onClick={onToggleSortOrder}
          title={sortAsc ? '当前正序，点击切换为倒序' : '当前倒序，点击切换为正序'}
          className="px-2 py-1.5 rounded-xl text-xs font-semibold inline-flex items-center gap-1 text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700 transition-all active:scale-95 cursor-pointer"
        >
          {sortAsc ? <ArrowUp className="w-3.5 h-3.5" /> : <ArrowDown className="w-3.5 h-3.5" />}
          <span>{sortAsc ? '正序' : '倒序'}</span>
        </button>
      </div>
      <div className="bg-slate-100 dark:bg-slate-800 p-1 rounded-2xl border border-slate-200 dark:border-slate-700 flex items-center gap-1 shadow-2xs">
        <button
          type="button"
          onClick={() => onViewModeChange('grid')}
          className={`px-3 py-1.5 rounded-xl text-xs font-semibold flex items-center gap-1.5 transition-all ${
            viewMode === 'grid'
              ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-xs'
              : 'text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200'
          }`}
          title="网格视图：封面卡片流，适合快速找内容"
        >
          <LayoutGrid className="w-3.5 h-3.5" />
          <span>网格视图</span>
        </button>
        <button
          type="button"
          onClick={() => onViewModeChange('list')}
          className={`px-3 py-1.5 rounded-xl text-xs font-semibold flex items-center gap-1.5 transition-all ${
            viewMode === 'list'
              ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-xs'
              : 'text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200'
          }`}
          title="列表视图：逐条信息核对，展现点赞/收藏与时间明细"
        >
          <List className="w-3.5 h-3.5" />
          <span>列表视图</span>
        </button>
      </div>
    </div>
  </div>
);

/** 多选模式批量操作条：全选所有/本页、下载所选、删除所选 */
export const BrowserSelectionBar: React.FC<{
  selectedCount: number;
  totalCount: number;
  selectingAll: boolean;
  allFilteredSelected: boolean;
  onToggleSelectAllFiltered: () => void;
  allPageSelected: boolean;
  onToggleSelectAllPage: () => void;
  onDownloadSelected: () => void;
  onDeleteSelected: () => void;
}> = ({
  selectedCount,
  totalCount,
  selectingAll,
  allFilteredSelected,
  onToggleSelectAllFiltered,
  allPageSelected,
  onToggleSelectAllPage,
  onDownloadSelected,
  onDeleteSelected,
}) => (
  <div className="bg-white dark:bg-[#161B26] p-3 rounded-2xl border border-violet-200/80 dark:border-violet-900 shadow-2xs flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
    <span className="font-semibold text-slate-700 dark:text-slate-200">
      已选 <strong className="text-violet-600">{selectedCount}</strong> 条收藏
      <span className="ml-2 text-[11px] text-slate-400 font-normal">点击卡片勾选，再次点击取消</span>
    </span>
    <div className="flex items-center gap-2 self-end sm:self-auto">
      <button
        type="button"
        onClick={onToggleSelectAllFiltered}
        disabled={selectingAll}
        title="选中当前过滤器命中的全部条目（跨页），再次点击取消全部"
        className="px-3.5 py-2 rounded-xl border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-50 disabled:cursor-wait text-slate-700 dark:text-slate-200 font-semibold inline-flex items-center gap-1.5 transition-all active:scale-95 cursor-pointer"
      >
        {selectingAll ? (
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
        ) : (
          <CheckSquare className="w-3.5 h-3.5" />
        )}
        {selectingAll
          ? '选取中...'
          : allFilteredSelected
            ? `取消全部 (${totalCount})`
            : `全选所有 (${totalCount})`}
      </button>
      <button
        type="button"
        onClick={onToggleSelectAllPage}
        className="px-3.5 py-2 rounded-xl border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-200 font-semibold inline-flex items-center gap-1.5 transition-all active:scale-95 cursor-pointer"
      >
        <CheckSquare className="w-3.5 h-3.5" />
        {allPageSelected ? '取消本页全选' : '全选本页'}
      </button>
      <button
        type="button"
        onClick={onDownloadSelected}
        disabled={selectedCount === 0}
        className="px-3.5 py-2 rounded-xl bg-sky-600 hover:bg-sky-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-bold inline-flex items-center gap-1.5 transition-all active:scale-95 cursor-pointer"
      >
        <Download className="w-3.5 h-3.5" />
        下载所选
      </button>
      <button
        type="button"
        onClick={onDeleteSelected}
        disabled={selectedCount === 0}
        className="px-3.5 py-2 rounded-xl bg-rose-600 hover:bg-rose-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-bold inline-flex items-center gap-1.5 transition-all active:scale-95 cursor-pointer"
      >
        <Trash2 className="w-3.5 h-3.5" />
        删除所选
      </button>
    </div>
  </div>
);
