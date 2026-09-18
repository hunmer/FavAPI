import React from 'react';
import { Database, ChevronLeft, ChevronRight } from 'lucide-react';
import { ScrapedItem } from '../../types';
import { coverApiUrl } from '../../api';
import { DataItemCard } from './DataItemCard';

/**
 * 内容区（自 DataBrowserView 抽离）：空态 / 网格视图 / 列表视图，
 * 含内部滚动区（#data-browser-scroll）与底部钉住的分页条。
 */
export const BrowserContent: React.FC<{
  listLoading: boolean;
  totalCount: number;
  totalAll: number;
  viewMode: 'grid' | 'list';
  currentItems: ScrapedItem[];
  selectionMode: boolean;
  selectedKeys: Set<string>;
  itemKey: (item: ScrapedItem) => string;
  onToggleSelectItem: (item: ScrapedItem) => void;
  allPageSelected: boolean;
  onToggleSelectAllPage: () => void;
  onOpenItem: (item: ScrapedItem) => void;
  onFilterAuthor: (author: string) => void;
  onOpenExternal: (item: ScrapedItem) => void;
  onCopyUrl: (item: ScrapedItem) => void;
  onOpenWithAccount: (item: ScrapedItem) => void;
  onDownload: (item: ScrapedItem) => void;
  onDeleteItem: (item: ScrapedItem) => void;
  onRowContextMenu: (x: number, y: number, item: ScrapedItem) => void;
  startIndex: number;
  endIndex: number;
  pageSize: number;
  onPageSizeChange: (n: number) => void;
  currentPage: number;
  totalPages: number;
  onGotoPage: (page: number) => void;
}> = ({
  listLoading,
  totalCount,
  totalAll,
  viewMode,
  currentItems,
  selectionMode,
  selectedKeys,
  itemKey,
  onToggleSelectItem,
  allPageSelected,
  onToggleSelectAllPage,
  onOpenItem,
  onFilterAuthor,
  onOpenExternal,
  onCopyUrl,
  onOpenWithAccount,
  onDownload,
  onDeleteItem,
  onRowContextMenu,
  startIndex,
  endIndex,
  pageSize,
  onPageSizeChange,
  currentPage,
  totalPages,
  onGotoPage,
}) => (
  <>
    <div
      id="data-browser-scroll"
      className={`flex-1 min-h-0 overflow-y-auto pb-20 lg:pb-0 transition-opacity ${listLoading ? 'opacity-50' : ''}`}
    >
    {totalCount === 0 ? (
      /* 空数据占位：区分全库为空与筛选无命中 */
      <div className="bg-white dark:bg-[#161B26] rounded-[28px] border border-dashed border-slate-200 dark:border-slate-800 py-20 flex flex-col items-center justify-center gap-3 text-center">
        <div className="w-14 h-14 rounded-3xl bg-slate-50 dark:bg-slate-800 text-slate-300 dark:text-slate-600 flex items-center justify-center">
          <Database className="w-7 h-7" />
        </div>
        <div className="text-sm font-bold text-slate-500 dark:text-slate-300">
          {totalAll === 0 ? '收藏库还是空的' : '没有符合条件的收藏'}
        </div>
        <p className="text-xs text-slate-400 max-w-xs leading-relaxed">
          {totalAll === 0
            ? '先到「账号管理」对平台账号执行一次抓取，数据入库后即可在这里浏览与打标。'
            : '试试调整左侧的账号、收藏夹、标签或搜索关键词。'}
        </p>
      </div>
    ) : viewMode === 'grid' ? (
      /* Grid View: Cover card stream with video metrics overlay */
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 sm:gap-5">
        {currentItems.map((item, idx) => (
          <DataItemCard
            key={item.id}
            item={item}
            idx={idx}
            onSelect={onOpenItem}
            selectable={selectionMode}
            selected={selectedKeys.has(itemKey(item))}
            onToggleSelect={onToggleSelectItem}
            onFilterAuthor={onFilterAuthor}
            onOpenExternal={onOpenExternal}
            onCopyUrl={onCopyUrl}
            onOpenWithAccount={onOpenWithAccount}
            onDownload={onDownload}
            onDelete={onDeleteItem}
          />
        ))}
      </div>
    ) : (
      /* List View: Detailed row inspection */
      <div className="bg-white dark:bg-[#161B26] rounded-[28px] border border-slate-200/80 dark:border-slate-800 shadow-2xs overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-slate-50/80 dark:bg-slate-800/60 text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-700 font-semibold">
                {selectionMode && (
                  <th className="py-3 px-4 w-10">
                    <input
                      type="checkbox"
                      checked={allPageSelected}
                      onChange={onToggleSelectAllPage}
                      className="w-4 h-4 rounded accent-violet-600 cursor-pointer"
                      title="全选/取消本页"
                    />
                  </th>
                )}
                <th className="py-3 px-4 w-16">封面</th>
                <th className="py-3 px-4">标题 (点击跳转原站)</th>
                <th className="py-3 px-4">作者 / UP主</th>
                <th className="py-3 px-4">时长</th>
                <th className="py-3 px-4 text-right">点赞 / 收藏</th>
                <th className="py-3 px-4">所属收藏夹</th>
                <th className="py-3 px-4">收藏时间</th>
                <th className="py-3 px-4">抓取入库时间</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {currentItems.map((item, idx) => {
                const rowSelected = selectionMode && selectedKeys.has(itemKey(item));
                return (
                <tr
                  key={item.id}
                  onClick={() => (selectionMode ? onToggleSelectItem(item) : onOpenItem(item))}
                  onContextMenu={(e) => {
                    e.preventDefault();
                    onRowContextMenu(e.clientX, e.clientY, item);
                  }}
                  className={`anim-row-enter cursor-pointer transition-colors ${
                    rowSelected
                      ? 'bg-violet-50/70 dark:bg-violet-950/60'
                      : 'hover:bg-slate-50/80 dark:hover:bg-slate-800/60'
                  }`}
                  style={{ animationDelay: `${Math.min(idx * 20, 200)}ms` }}
                >
                  {selectionMode && (
                    <td className="py-2.5 px-4" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={rowSelected}
                        onChange={() => onToggleSelectItem(item)}
                        className="w-4 h-4 rounded accent-violet-600 cursor-pointer"
                      />
                    </td>
                  )}
                  <td className="py-2.5 px-4">
                    <img
                      src={coverApiUrl(item.platform, item.id)}
                      alt=""
                      className="w-14 h-9 rounded-lg object-cover bg-slate-200 shrink-0"
                      referrerPolicy="no-referrer"
                    />
                  </td>
                  <td className="py-2.5 px-4 max-w-sm">
                    <a
                      href={item.url}
                      target="_blank"
                      rel="noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      className="font-bold text-slate-900 dark:text-white hover:text-indigo-600 dark:hover:text-indigo-400 line-clamp-2"
                    >
                      {item.title}
                    </a>
                    {item.tags && item.tags.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-1">
                        {item.tags.slice(0, 4).map((t) => (
                          <span
                            key={t}
                            className="px-1.5 py-0.5 rounded bg-violet-50 dark:bg-violet-950 text-violet-600 dark:text-violet-400 text-[10px] font-medium border border-violet-100 dark:border-violet-900"
                          >
                            #{t}
                          </span>
                        ))}
                      </div>
                    )}
                    <div className="text-[10px] text-slate-400 mt-0.5 flex items-center gap-1.5">
                      <span>{item.accountName}</span>
                    </div>
                  </td>
                  <td className="py-2.5 px-4 font-medium text-slate-800 dark:text-slate-200 whitespace-nowrap">
                    {item.author}
                  </td>
                  <td className="py-2.5 px-4 font-mono text-slate-600 dark:text-slate-400 whitespace-nowrap">
                    {item.duration || '—'}
                  </td>
                  <td className="py-2.5 px-4 text-right whitespace-nowrap font-medium text-slate-700 dark:text-slate-200">
                    <div>{(item.likes / 1000).toFixed(1)}k 赞</div>
                    <div className="text-[10px] text-slate-400">{(item.favorites / 1000).toFixed(1)}k 藏</div>
                  </td>
                  <td className="py-2.5 px-4 whitespace-nowrap">
                    <span className="px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 font-medium">
                      {item.folderName}
                    </span>
                    {item.sourceName && item.sourceName !== '收藏列表' && (
                      <span className="ml-1.5 px-2 py-0.5 rounded bg-indigo-600 text-white text-[11px] font-semibold">
                        {item.sourceName}
                      </span>
                    )}
                  </td>
                  <td className="py-2.5 px-4 text-slate-500 dark:text-slate-400 whitespace-nowrap">
                    {item.favTime}
                  </td>
                  <td className="py-2.5 px-4 text-slate-400 dark:text-slate-500 text-[11px] whitespace-nowrap">
                    {item.crawlTime}
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    )}
    </div>

    {/* Pagination Footer（无数据时隐藏；sticky 于 main 滚动视口底部，卡片圆角样式，不脱离容器） */}
    {totalCount > 0 && (
    <div className="sticky bottom-4 z-20 bg-white dark:bg-[#161B26] p-4 rounded-2xl border border-slate-200/80 dark:border-slate-800 shadow-lg flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs text-slate-600 dark:text-slate-300">
      <div className="flex items-center gap-3">
        <span>
          显示第 <strong className="text-slate-900 dark:text-white">{startIndex + 1}</strong> 到{' '}
          <strong className="text-slate-900 dark:text-white">{endIndex}</strong> 条，共{' '}
          <strong className="text-slate-900 dark:text-white">{totalCount}</strong> 条已入库收藏
        </span>

        <div className="flex items-center gap-1">
          <span className="text-slate-400">每页:</span>
          <select
            value={pageSize}
            onChange={(e) => onPageSizeChange(Number(e.target.value))}
            className="px-2 py-1 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-700 dark:text-slate-200 font-semibold"
          >
            <option value="20">20 条</option>
            <option value="50">50 条</option>
            <option value="100">100 条</option>
            <option value="200">200 条</option>
          </select>
        </div>
      </div>

      {/* Page controls */}
      <div className="flex items-center gap-1.5 self-end sm:self-auto">
        <button
          type="button"
          disabled={currentPage <= 1}
          onClick={() => onGotoPage(currentPage - 1)}
          className="p-1.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 hover:bg-slate-100 dark:hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed shadow-2xs"
          title="上一页"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
        <span className="px-3 py-1 font-semibold text-slate-800 dark:text-slate-200">
          {currentPage} / {totalPages}
        </span>
        <button
          type="button"
          disabled={currentPage >= totalPages}
          onClick={() => onGotoPage(currentPage + 1)}
          className="p-1.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 hover:bg-slate-100 dark:hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed shadow-2xs"
          title="下一页"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    </div>
    )}
  </>
);
