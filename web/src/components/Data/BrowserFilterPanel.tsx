import React, { useState } from 'react';
import {
  Search,
  X,
  ChevronDown,
  User,
  Clock,
  CalendarDays,
  Layers,
  Tag,
  Plus,
  CheckCircle2,
  Pencil,
  ChevronRight,
} from 'lucide-react';
import { Account } from '../../types';
import { SiteIcon } from '../SiteIcon';
import { DropdownSelect } from '../DropdownSelect';
import * as api from '../../api';

/** 过滤器标题行右侧的清空小图标按钮 */
const FilterClearBtn: React.FC<{ onClick: () => void; title: string }> = ({ onClick, title }) => (
  <button
    type="button"
    onClick={onClick}
    title={title}
    className="w-5 h-5 rounded-full bg-slate-100 dark:bg-slate-800 hover:bg-rose-100 dark:hover:bg-rose-950 text-slate-400 hover:text-rose-500 flex items-center justify-center transition-colors cursor-pointer shrink-0"
  >
    <X className="w-3 h-3" />
  </button>
);

/** 左侧过滤面板（自 DataBrowserView 抽离）：搜索/账号/来源/作者/入库与发布日期/AI 标签分组 */
export const BrowserFilterPanel: React.FC<{
  accounts: Account[];
  accountCounts: Map<string, number>;
  totalAll: number;
  totalCount: number;
  selectedAccountId: string;
  /** 切换账号（同时重置来源与作者过滤，由父组件组合处理） */
  onSelectAccount: (id: string) => void;
  searchQuery: string;
  onSearchQueryChange: (q: string) => void;
  sourceFacets: Array<[string, number]>;
  selectedSource: string;
  onSelectSource: (source: string) => void;
  authorFacets: Array<[string, number]>;
  selectedAuthor: string;
  onSelectAuthor: (author: string) => void;
  selectedDate: string;
  selectedEndDate: string;
  onDateRangeChange: (start: string, end: string) => void;
  selectedPubDate: string;
  selectedPubEndDate: string;
  onPubStartChange: (v: string) => void;
  onPubEndChange: (v: string) => void;
  tagStats: api.TagStatRow[];
  tagGroups: api.TagGroupRow[];
  selectedTags: string[];
  onToggleTag: (t: string) => void;
  onClearTags: () => void;
  onTagContextMenu: (x: number, y: number, tag: string) => void;
  editingGroup: { group: string; value: string } | null;
  onEditingGroupChange: (g: { group: string; value: string } | null) => void;
  groupSaving: boolean;
  onSubmitGroupRename: () => void;
  onOpenGroupCreate: () => void;
  hasActiveFilters: boolean;
  onClearAllFilters: () => void;
}> = ({
  accounts,
  accountCounts,
  totalAll,
  totalCount,
  selectedAccountId,
  onSelectAccount,
  searchQuery,
  onSearchQueryChange,
  sourceFacets,
  selectedSource,
  onSelectSource,
  authorFacets,
  selectedAuthor,
  onSelectAuthor,
  selectedDate,
  selectedEndDate,
  onDateRangeChange,
  selectedPubDate,
  selectedPubEndDate,
  onPubStartChange,
  onPubEndChange,
  tagStats,
  tagGroups,
  selectedTags,
  onToggleTag,
  onClearTags,
  onTagContextMenu,
  editingGroup,
  onEditingGroupChange,
  groupSaving,
  onSubmitGroupRename,
  onOpenGroupCreate,
  hasActiveFilters,
  onClearAllFilters,
}) => {
  // 来源/作者折叠列表与分组折叠纯 UI 状态，仅面板内使用
  const [sourceListOpen, setSourceListOpen] = useState(false);
  const [authorListOpen, setAuthorListOpen] = useState(false);
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({});

  return (
    <aside className="w-full lg:w-60 xl:w-64 shrink-0 lg:self-stretch">
      <div className="lg:sticky lg:top-4 lg:max-h-full bg-white dark:bg-[#161B26] rounded-3xl border border-slate-200/80 dark:border-slate-800 shadow-2xs flex flex-col overflow-hidden">
        <div className="lg:overflow-y-auto p-4 flex flex-col gap-4">
        {/* Search */}
        <div className="relative">
          <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchQueryChange(e.target.value)}
            placeholder="搜索标题、UP主、标签..."
            className={`w-full pl-8 ${searchQuery ? 'pr-8' : 'pr-3'} py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-xs focus:outline-none focus:ring-2 focus:ring-slate-900 bg-slate-50/50 dark:bg-slate-800 dark:text-slate-200`}
          />
          {searchQuery && (
            <button
              type="button"
              onClick={() => onSearchQueryChange('')}
              className="absolute right-2 top-1/2 -translate-y-1/2 w-5 h-5 rounded-full bg-slate-200 dark:bg-slate-700 hover:bg-slate-300 dark:hover:bg-slate-600 text-slate-500 dark:text-slate-300 hover:text-slate-700 dark:hover:text-slate-100 flex items-center justify-center transition-colors cursor-pointer"
              title="清空搜索"
            >
              <X className="w-3 h-3" />
            </button>
          )}
        </div>

        {/* Account selector */}
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-600 dark:text-slate-400 uppercase tracking-wider">账号</span>
            {selectedAccountId !== 'all' && (
              <FilterClearBtn title="清除账号过滤" onClick={() => onSelectAccount('all')} />
            )}
          </div>
          <DropdownSelect
            value={selectedAccountId}
            onChange={onSelectAccount}
            options={[
              { id: 'all', label: '全部账号', count: totalAll },
              ...accounts.map((acc) => ({
                id: acc.id,
                label: acc.name,
                count: accountCounts.get(acc.id) ?? 0,
                icon: <SiteIcon platform={acc.platform} name={acc.name} className="w-3.5 h-3.5" />,
              })),
            ]}
          />
        </div>

        {/* Source selector（入库来源：收藏/喜欢/稍后再看列表，存在非默认来源时显示） */}
        {sourceFacets.some(([name]) => name !== '收藏列表') && (
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-slate-600 dark:text-slate-400 uppercase tracking-wider">来源</span>
              {selectedSource !== 'all' && (
                <FilterClearBtn title="清除来源过滤" onClick={() => onSelectSource('all')} />
              )}
            </div>
            <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 overflow-hidden">
              <button
                type="button"
                onClick={() => setSourceListOpen((v) => !v)}
                className="w-full px-3 py-2 flex items-center justify-between gap-2 text-xs font-medium text-slate-800 dark:text-slate-200 cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
              >
                <span className="flex items-center gap-1.5 min-w-0">
                  <Layers
                    className={`w-3.5 h-3.5 shrink-0 ${selectedSource === 'all' ? 'text-slate-400' : 'text-indigo-500'}`}
                  />
                  <span className="truncate">
                    {selectedSource === 'all' ? '全部来源' : selectedSource}
                  </span>
                </span>
                <ChevronDown
                  className={`w-3.5 h-3.5 text-slate-400 shrink-0 transition-transform ${sourceListOpen ? 'rotate-180' : ''}`}
                />
              </button>
              {sourceListOpen && (
                <div className="border-t border-slate-100 dark:border-slate-700 max-h-52 overflow-y-auto bg-white dark:bg-slate-800">
                  <button
                    type="button"
                    onClick={() => {
                      onSelectSource('all');
                      setSourceListOpen(false);
                    }}
                    className={`w-full px-3 py-2 flex items-center gap-1.5 text-xs cursor-pointer transition-colors ${
                      selectedSource === 'all'
                        ? 'bg-violet-50 dark:bg-violet-950 text-violet-700 dark:text-violet-400 font-semibold'
                        : 'text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700'
                    }`}
                  >
                    <Layers className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                    <span className="truncate">全部来源</span>
                  </button>
                  {sourceFacets.map(([name, count]) => (
                    <button
                      key={name}
                      type="button"
                      onClick={() => {
                        onSelectSource(name);
                        setSourceListOpen(false);
                      }}
                      className={`w-full px-3 py-2 flex items-center gap-1.5 text-xs cursor-pointer transition-colors ${
                        selectedSource === name
                          ? 'bg-violet-50 dark:bg-violet-950 text-violet-700 dark:text-violet-400 font-semibold'
                          : 'text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700'
                      }`}
                    >
                      <Layers className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
                      <span className="truncate">
                        {name} ({count})
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Author selector（与收藏夹选择器同款交互，点击卡片作者名可快捷应用） */}
        {authorFacets.length > 0 && (
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-slate-600 dark:text-slate-400 uppercase tracking-wider">作者 / UP主</span>
              {selectedAuthor !== 'all' && (
                <FilterClearBtn title="清除作者过滤" onClick={() => onSelectAuthor('all')} />
              )}
            </div>
            <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 overflow-hidden">
              <button
                type="button"
                onClick={() => setAuthorListOpen((v) => !v)}
                className="w-full px-3 py-2 flex items-center justify-between gap-2 text-xs font-medium text-slate-800 dark:text-slate-200 cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
              >
                <span className="flex items-center gap-1.5 min-w-0">
                  <User
                    className={`w-3.5 h-3.5 shrink-0 ${selectedAuthor === 'all' ? 'text-slate-400' : 'text-violet-500'}`}
                  />
                  <span className="truncate">
                    {selectedAuthor === 'all' ? '全部作者' : selectedAuthor}
                  </span>
                </span>
                <ChevronDown
                  className={`w-3.5 h-3.5 text-slate-400 shrink-0 transition-transform ${authorListOpen ? 'rotate-180' : ''}`}
                />
              </button>
              {authorListOpen && (
                <div className="border-t border-slate-100 dark:border-slate-700 max-h-52 overflow-y-auto bg-white dark:bg-slate-800">
                  <button
                    type="button"
                    onClick={() => {
                      onSelectAuthor('all');
                      setAuthorListOpen(false);
                    }}
                    className={`w-full px-3 py-2 flex items-center gap-1.5 text-xs cursor-pointer transition-colors ${
                      selectedAuthor === 'all'
                        ? 'bg-violet-50 dark:bg-violet-950 text-violet-700 dark:text-violet-400 font-semibold'
                        : 'text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700'
                    }`}
                  >
                    <User className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                    <span className="truncate">全部作者</span>
                  </button>
                  {authorFacets.map(([author, count]) => (
                    <button
                      key={author}
                      type="button"
                      onClick={() => {
                        onSelectAuthor(author);
                        setAuthorListOpen(false);
                      }}
                      className={`w-full px-3 py-2 flex items-center gap-1.5 text-xs cursor-pointer transition-colors ${
                        selectedAuthor === author
                          ? 'bg-violet-50 dark:bg-violet-950 text-violet-700 dark:text-violet-400 font-semibold'
                          : 'text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700'
                      }`}
                    >
                      <User className="w-3.5 h-3.5 text-violet-400 shrink-0" />
                      <span className="truncate">
                        {author} ({count})
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Crawl date filter（按抓取入库时间过滤） */}
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-600 dark:text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
              <Clock className="w-3 h-3 text-sky-500" />
              入库日期
            </span>
            {(selectedDate || selectedEndDate) && (
              <FilterClearBtn title="清除日期过滤" onClick={() => onDateRangeChange('', '')} />
            )}
          </div>
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] text-slate-400 w-5 shrink-0 text-center">起</span>
              <input
                type="date"
                value={selectedDate}
                max={selectedEndDate || undefined}
                onChange={(e) => onDateRangeChange(e.target.value, selectedEndDate)}
                className="flex-1 min-w-0 px-2 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-xs bg-slate-50 dark:bg-slate-800 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-slate-900 font-medium cursor-pointer"
              />
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] text-slate-400 w-5 shrink-0 text-center">止</span>
              <input
                type="date"
                value={selectedEndDate}
                min={selectedDate || undefined}
                onChange={(e) => onDateRangeChange(selectedDate, e.target.value)}
                className="flex-1 min-w-0 px-2 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-xs bg-slate-50 dark:bg-slate-800 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-slate-900 font-medium cursor-pointer"
              />
            </div>
          </div>
          <p className="text-[10px] text-slate-400">
            按抓取入库时间过滤，可只填一端；总览日历卡可一键跳转带入。
          </p>
        </div>

        {/* Publish date filter（按作品发布时间过滤，取自内容元数据） */}
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-600 dark:text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
              <CalendarDays className="w-3 h-3 text-emerald-500" />
              发布时间
            </span>
            {(selectedPubDate || selectedPubEndDate) && (
              <FilterClearBtn
                title="清除发布时间过滤"
                onClick={() => {
                  onPubStartChange('');
                  onPubEndChange('');
                }}
              />
            )}
          </div>
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] text-slate-400 w-5 shrink-0 text-center">起</span>
              <input
                type="date"
                value={selectedPubDate}
                max={selectedPubEndDate || undefined}
                onChange={(e) => onPubStartChange(e.target.value)}
                className="flex-1 min-w-0 px-2 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-xs bg-slate-50 dark:bg-slate-800 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-slate-900 font-medium cursor-pointer"
              />
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] text-slate-400 w-5 shrink-0 text-center">止</span>
              <input
                type="date"
                value={selectedPubEndDate}
                min={selectedPubDate || undefined}
                onChange={(e) => onPubEndChange(e.target.value)}
                className="flex-1 min-w-0 px-2 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-xs bg-slate-50 dark:bg-slate-800 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-slate-900 font-medium cursor-pointer"
              />
            </div>
          </div>
          <p className="text-[10px] text-slate-400">
            按作品在源平台的发布时间过滤；小红书等无发布时间数据的内容会被排除。
          </p>
        </div>

        {/* AI 标签：按体系分组展示，badge 多选（OR）*/}
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-600 dark:text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
              <Tag className="w-3 h-3 text-violet-500" />
              AI 标签
            </span>
            <div className="flex items-center gap-2.5">
              {selectedTags.length > 0 && (
                <FilterClearBtn
                  title={`清除标签过滤（已选 ${selectedTags.length} 个）`}
                  onClick={onClearTags}
                />
              )}
              <button
                type="button"
                onClick={onOpenGroupCreate}
                className="w-6 h-6 rounded-lg bg-violet-50 dark:bg-violet-950 border border-violet-100 dark:border-violet-900 text-violet-500 dark:text-violet-400 hover:bg-violet-100 dark:hover:bg-violet-900 hover:text-violet-600 flex items-center justify-center transition-all active:scale-95 cursor-pointer"
                title="新建标签分组"
              >
                <Plus className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
          {(() => {
            const countByTag = new Map(tagStats.map((t) => [t.tag, t.count]));
            return (
              <div className="flex flex-col gap-2.5 max-h-96 overflow-y-auto pr-0.5">
                {tagGroups.map((g) => {
                  const groupSelected = g.tags.filter((t) => selectedTags.includes(t)).length;
                  const collapsed = collapsedGroups[g.group];
                  const isEditing = editingGroup?.group === g.group;
                  const isOther = g.group === '其他';
                  return (
                    <div key={g.group}>
                      {isEditing ? (
                        /* 组名行内编辑 */
                        <div className="flex items-center gap-1 py-0.5">
                          <input
                            autoFocus
                            type="text"
                            value={editingGroup.value}
                            onChange={(e) => onEditingGroupChange({ group: g.group, value: e.target.value })}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') onSubmitGroupRename();
                              if (e.key === 'Escape') onEditingGroupChange(null);
                            }}
                            className="flex-1 min-w-0 px-2 py-1 rounded-lg border border-violet-300 dark:border-violet-700 bg-transparent text-[11px] font-bold text-slate-700 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-violet-500"
                          />
                          <button
                            type="button"
                            onClick={onSubmitGroupRename}
                            disabled={groupSaving}
                            className="p-1 rounded-md text-emerald-600 hover:bg-emerald-50 disabled:opacity-50 cursor-pointer"
                            title="保存"
                          >
                            <CheckCircle2 className="w-3.5 h-3.5" />
                          </button>
                          <button
                            type="button"
                            onClick={() => onEditingGroupChange(null)}
                            className="p-1 rounded-md text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 cursor-pointer"
                            title="取消"
                          >
                            <X className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      ) : (
                        <div className="w-full flex items-center justify-between py-0.5 group/head">
                          <button
                            type="button"
                            onClick={() => setCollapsedGroups((prev) => ({ ...prev, [g.group]: !collapsed }))}
                            className="flex items-center gap-1 text-[11px] font-bold text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200 transition-colors cursor-pointer"
                          >
                            {g.group}
                            {groupSelected > 0 && (
                              <span className="px-1.5 rounded-full bg-violet-600 text-white text-[9px] leading-4">
                                {groupSelected}
                              </span>
                            )}
                          </button>
                          <div className="flex items-center gap-0.5">
                            {!isOther && (
                              <button
                                type="button"
                                onClick={() => onEditingGroupChange({ group: g.group, value: g.group })}
                                className="p-0.5 rounded text-slate-300 hover:text-slate-600 opacity-0 group-hover/head:opacity-100 transition-all cursor-pointer"
                                title="重命名分组"
                              >
                                <Pencil className="w-3 h-3" />
                              </button>
                            )}
                            <button
                              type="button"
                              onClick={() => setCollapsedGroups((prev) => ({ ...prev, [g.group]: !collapsed }))}
                              className="p-0.5 text-slate-400 cursor-pointer"
                            >
                              <ChevronRight
                                className={`w-3 h-3 transition-transform ${collapsed ? '' : 'rotate-90'}`}
                              />
                            </button>
                          </div>
                        </div>
                      )}
                      {!collapsed && (
                        <div className="flex flex-wrap gap-1.5 mt-1.5">
                          {g.tags.map((t) => {
                            const active = selectedTags.includes(t);
                            const count = countByTag.get(t);
                            return (
                              <button
                                key={t}
                                type="button"
                                onClick={() => onToggleTag(t)}
                                onContextMenu={(e) => {
                                  e.preventDefault();
                                  e.stopPropagation();
                                  onTagContextMenu(e.clientX, e.clientY, t);
                                }}
                                title="左键筛选 · 右键管理"
                                className={`px-2 py-1 rounded-lg text-[11px] font-medium border transition-all cursor-pointer active:scale-95 ${
                                  active
                                    ? 'bg-violet-600 text-white border-violet-600 shadow-xs'
                                    : count
                                      ? 'bg-violet-50/60 dark:bg-violet-950 text-violet-600 dark:text-violet-400 border-violet-100 dark:border-violet-900 hover:bg-violet-100 dark:hover:bg-violet-900 hover:border-violet-200'
                                      : 'bg-slate-50 dark:bg-slate-800 text-slate-400 dark:text-slate-500 border-slate-100 dark:border-slate-700 hover:border-slate-200 hover:text-slate-500'
                                }`}
                              >
                                #{t}
                                {count ? (
                                  <span className={`ml-1 text-[10px] ${active ? 'text-white/70' : 'text-violet-400'}`}>
                                    {count}
                                  </span>
                                ) : null}
                              </button>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            );
          })()}
        </div>

        {/* 筛选统计小结 */}
        <div className="pt-3 border-t border-slate-100 dark:border-slate-800 text-[11px] text-slate-400">
          命中 <strong className="text-slate-700 dark:text-slate-200">{totalCount}</strong> / {totalAll} 条
          {(selectedDate || selectedEndDate) && (
            <span>（入库 {selectedDate || '…'} ~ {selectedEndDate || '…'}）</span>
          )}
          {(selectedPubDate || selectedPubEndDate) && (
            <span>（发布 {selectedPubDate || '…'} ~ {selectedPubEndDate || '…'}）</span>
          )}
          {selectedAuthor !== 'all' && <span>（作者：{selectedAuthor}）</span>}
          {selectedSource !== 'all' && <span>（来源：{selectedSource}）</span>}
          {selectedTags.length > 0 && <span>（含任一选中标签）</span>}
        </div>
        </div>

        {/* 清空全部过滤（常驻面板底部固定，不随过滤项滚动；无激活过滤时禁用） */}
        <div className="p-3 border-t border-slate-100 dark:border-slate-800">
          <button
            type="button"
            onClick={onClearAllFilters}
            disabled={!hasActiveFilters}
            className="w-full px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 hover:border-rose-200 hover:bg-rose-50 dark:hover:bg-rose-950 text-slate-500 dark:text-slate-400 hover:text-rose-600 text-xs font-bold shadow-2xs inline-flex items-center justify-center gap-1.5 transition-all active:scale-95 cursor-pointer disabled:opacity-40 disabled:pointer-events-none"
          >
            <X className="w-3.5 h-3.5" />
            清空全部过滤
          </button>
        </div>
      </div>
    </aside>
  );
};
