import React from 'react';
import { ScrapedItem } from '../../../types';
import { Terminal } from 'lucide-react';

interface ScrapeStreamProps {
  streamingItems: ScrapedItem[];
  isScrapingInProgress: boolean;
}

/** 抓取实时反馈流：增量入库的收藏条目滚动展示（抓一条看一条） */
export const ScrapeStream: React.FC<ScrapeStreamProps> = ({ streamingItems, isScrapingInProgress }) => {
  if (!isScrapingInProgress && streamingItems.length === 0) return null;

  return (
    <div className="mt-8 pt-6 border-t border-slate-200">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h4 className="text-sm font-bold text-slate-900 flex items-center gap-2">
            <Terminal className="w-4 h-4 text-emerald-600" />
            抓取实时反馈流 (已抓取 {streamingItems.length} 条)
          </h4>
          <p className="text-xs text-slate-400 mt-0.5">
            增量入库完成，支持点击标题直接预览原站页面
          </p>
        </div>
        <div className="text-xs font-mono text-slate-500 bg-slate-100 px-3 py-1 rounded-xl">
          {isScrapingInProgress ? '抓取中...' : '已完成'}
        </div>
      </div>

      {/* Items stream */}
      <div className="space-y-2.5 max-h-96 overflow-y-auto pr-1">
        {streamingItems.map((item, idx) => (
          <div
            key={item.id + idx}
            className="p-3 bg-slate-50/80 rounded-xl border border-slate-200/80 flex items-center justify-between gap-3 text-xs hover:bg-slate-100 transition-colors"
          >
            <div className="flex items-center gap-3 min-w-0">
              {item.coverUrl ? (
                <img
                  src={item.coverUrl}
                  alt=""
                  className="w-12 h-8 rounded-lg object-cover bg-slate-200 shrink-0"
                  referrerPolicy="no-referrer"
                />
              ) : (
                <div className="w-12 h-8 rounded-lg bg-slate-200 shrink-0" />
              )}
              <div className="min-w-0">
                <a
                  href={item.url}
                  target="_blank"
                  rel="noreferrer"
                  className="font-semibold text-slate-900 hover:text-indigo-600 truncate block text-xs sm:text-sm"
                >
                  {item.title}
                </a>
                <div className="text-[11px] text-slate-500 flex items-center gap-2 mt-0.5">
                  <span>UP: {item.author}</span>
                  <span>•</span>
                  <span>{item.duration}</span>
                  <span>•</span>
                  <span className="text-slate-400">所属: {item.folderName}</span>
                </div>
              </div>
            </div>

            <div className="text-right shrink-0">
              <span className="text-[11px] text-emerald-600 font-bold bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                新增收藏
              </span>
              <div className="text-[10px] text-slate-400 mt-1">{item.favTime}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
