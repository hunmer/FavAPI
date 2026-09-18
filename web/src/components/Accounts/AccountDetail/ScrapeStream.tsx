import React from 'react';
import { ScrapedItem } from '../../../types';
import { Terminal } from 'lucide-react';

interface ScrapeStreamProps {
  streamingItems: ScrapedItem[];
  isScrapingInProgress: boolean;
}

/** 抓取实时反馈流：增量入库的收藏条目滚动展示（抓一条看一条） */
export const ScrapeStream: React.FC<ScrapeStreamProps> = ({ streamingItems, isScrapingInProgress }) => {
  const [showSkipped, setShowSkipped] = React.useState(false);

  if (!isScrapingInProgress && streamingItems.length === 0) return null;

  // 跳过项 = 库中已存在的条目（isNew === false），默认隐藏
  const skippedItems = streamingItems.filter((it) => it.isNew === false);
  const visibleItems = showSkipped ? streamingItems : streamingItems.filter((it) => it.isNew !== false);

  return (
    <div className="mt-8 pt-6 border-t border-slate-200 dark:border-slate-800">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h4 className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-2">
            <Terminal className="w-4 h-4 text-emerald-600" />
            抓取实时反馈流 (已抓取 {streamingItems.length} 条)
          </h4>
          <p className="text-xs text-slate-400 mt-0.5">
            增量入库完成，支持点击标题直接预览原站页面
          </p>
        </div>
        <div className="flex items-center gap-3">
          {skippedItems.length > 0 && (
            <label className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={showSkipped}
                onChange={(e) => setShowSkipped(e.target.checked)}
                className="w-3.5 h-3.5 rounded text-sky-600 border-slate-300 dark:border-slate-700 focus:ring-sky-500 cursor-pointer"
              />
              显示跳过项 ({skippedItems.length})
            </label>
          )}
          <div className="text-xs font-mono text-slate-500 dark:text-slate-400 bg-slate-100 dark:bg-slate-800 px-3 py-1 rounded-xl">
            {isScrapingInProgress ? '抓取中...' : '已完成'}
          </div>
        </div>
      </div>

      {/* Items stream */}
      <div className="space-y-2.5 max-h-96 overflow-y-auto pr-1">
        {visibleItems.length === 0 && (
          <div className="text-xs text-slate-400 text-center py-6">
            本批均为已存在条目，勾选「显示跳过项」查看
          </div>
        )}
        {visibleItems.map((item, idx) => (
          <div
            key={item.id + idx}
            className="p-3 bg-slate-50/80 dark:bg-slate-800/60 rounded-xl border border-slate-200/80 dark:border-slate-700 flex items-center justify-between gap-3 text-xs hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          >
            <div className="flex items-center gap-3 min-w-0">
              {item.coverUrl ? (
                <img
                  src={item.coverUrl}
                  alt=""
                  className="w-12 h-8 rounded-lg object-cover bg-slate-200 dark:bg-slate-700 shrink-0"
                  referrerPolicy="no-referrer"
                />
              ) : (
                <div className="w-12 h-8 rounded-lg bg-slate-200 dark:bg-slate-700 shrink-0" />
              )}
              <div className="min-w-0">
                <a
                  href={item.url}
                  target="_blank"
                  rel="noreferrer"
                  className="font-semibold text-slate-900 dark:text-white hover:text-indigo-600 dark:hover:text-indigo-400 truncate block text-xs sm:text-sm"
                >
                  {item.title}
                </a>
                <div className="text-[11px] text-slate-500 dark:text-slate-400 flex items-center gap-2 mt-0.5">
                  <span>UP: {item.author}</span>
                  <span>•</span>
                  <span>{item.duration}</span>
                  <span>•</span>
                  <span className="text-slate-400">所属: {item.folderName}</span>
                </div>
              </div>
            </div>

            <div className="text-right shrink-0">
              {item.isNew === false ? (
                <span className="text-[11px] text-slate-500 dark:text-slate-400 font-bold bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded-full border border-slate-200 dark:border-slate-700">
                  已存在
                </span>
              ) : (
                <span className="text-[11px] text-emerald-600 dark:text-emerald-400 font-bold bg-emerald-50 dark:bg-emerald-950 px-2 py-0.5 rounded-full border border-emerald-200 dark:border-emerald-800">
                  新增收藏
                </span>
              )}
              <div className="text-[10px] text-slate-400 mt-1">{item.favTime}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
