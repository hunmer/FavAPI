import React, { useState, useMemo } from 'react';
import {
  ChevronLeft,
  ChevronRight,
  Calendar as CalendarIcon,
  ExternalLink,
  Folder,
  Sparkles,
  Inbox,
  ArrowRight,
  Clock
} from 'lucide-react';
import { ScrapedItem } from '../../types';
import { PLATFORMS } from '../../data/platforms';

interface CalendarCardProps {
  scrapedItems?: ScrapedItem[];
  onViewAllData?: (date?: string) => void;
  onSelectItem?: (item: ScrapedItem) => void;
}

const WEEK_HEADERS = ['一', '二', '三', '四', '五', '六', '日'];

// 列表最多直接展示条数，超出引导跳转收藏数据中心
const MAX_VISIBLE_ITEMS = 20;

const pad = (n: number) => String(n).padStart(2, '0');

export const CalendarCard: React.FC<CalendarCardProps> = ({
  scrapedItems = [],
  onViewAllData,
  onSelectItem
}) => {
  const today = new Date();
  const [view, setView] = useState({ year: today.getFullYear(), month: today.getMonth() }); // month: 0-indexed
  const [selectedDay, setSelectedDay] = useState(today.getDate());

  const { year, month } = view;

  const goMonth = (delta: number) => {
    setView((prev) => {
      const d = new Date(prev.year, prev.month + delta, 1);
      return { year: d.getFullYear(), month: d.getMonth() };
    });
  };

  const daysInMonth = new Date(year, month + 1, 0).getDate();
  // 周一为一周起点（0=Mon）
  const startDayOffset = (new Date(year, month, 1).getDay() + 6) % 7;
  const monthPrefix = `${year}-${pad(month + 1)}`;
  const isToday = (day: number) =>
    year === today.getFullYear() && month === today.getMonth() && day === today.getDate();

  // 有入库记录的日期（按抓取时间）
  const activityDays = useMemo(() => {
    const days = new Set<number>();
    scrapedItems.forEach((item) => {
      const m = (item.crawlTime || '').match(/^(\d{4})-(\d{2})-(\d{2})/);
      if (m && `${m[1]}-${m[2]}` === monthPrefix) {
        days.add(parseInt(m[3], 10));
      }
    });
    return days;
  }, [scrapedItems, monthPrefix]);

  const selectedDateStr = `${monthPrefix}-${pad(selectedDay)}`;
  const dayItems = useMemo(
    () => scrapedItems.filter((item) => (item.crawlTime || '').startsWith(selectedDateStr)),
    [scrapedItems, selectedDateStr]
  );
  const visibleItems = dayItems.slice(0, MAX_VISIBLE_ITEMS);
  const hiddenCount = dayItems.length - visibleItems.length;

  const handleDayClick = (day: number) => {
    setSelectedDay(day);
  };

  return (
    <div className="bg-white dark:bg-[#161B26] rounded-3xl p-5 border border-slate-100 dark:border-slate-800 shadow-sm flex flex-col">
      {/* Calendar Header with Month and Prev/Next */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-xl bg-sky-50 dark:bg-sky-950/60 text-sky-600 dark:text-sky-400 flex items-center justify-center">
            <CalendarIcon className="w-4 h-4" />
          </div>
          <div>
            <span className="text-sm font-bold text-slate-800 dark:text-slate-100">{year}年 {month + 1}月</span>
            <span className="text-[10px] text-slate-400 ml-2 hidden sm:inline">归档时间线</span>
          </div>
        </div>

        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => goMonth(-1)}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer"
            title="上个月"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={() => goMonth(1)}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer"
            title="下个月"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Weekday headers */}
      <div className="grid grid-cols-7 gap-1 text-center mb-1.5">
        {WEEK_HEADERS.map((w, idx) => (
          <span key={idx} className="text-[11px] font-semibold text-slate-400 dark:text-slate-400 py-0.5">
            {w}
          </span>
        ))}
      </div>

      {/* Days Grid */}
      <div className="grid grid-cols-7 gap-1 text-center">
        {/* Empty cells for start offset */}
        {Array.from({ length: startDayOffset }).map((_, idx) => (
          <div key={`empty-${idx}`} className="h-8" />
        ))}

        {Array.from({ length: daysInMonth }, (_, i) => i + 1).map((day) => {
          const isSelected = day === selectedDay;
          const isTodayFlag = isToday(day);
          const hasActivity = activityDays.has(day);

          return (
            <button
              key={day}
              type="button"
              onClick={() => handleDayClick(day)}
              className={`h-8 w-8 mx-auto rounded-xl flex flex-col items-center justify-center relative text-xs font-semibold transition-all duration-150 cursor-pointer ${
                isSelected
                  ? 'bg-slate-900 dark:bg-sky-500 text-white shadow-md shadow-slate-900/20 dark:shadow-sky-500/30 scale-105'
                  : isTodayFlag
                  ? 'bg-sky-50 dark:bg-sky-950/60 text-sky-700 dark:text-sky-300 border border-sky-200 dark:border-sky-800'
                  : 'text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'
              }`}
            >
              <span>{day}</span>
              {/* Activity Dot */}
              {hasActivity && !isSelected && (
                <span className="absolute bottom-1 w-1 h-1 rounded-full bg-sky-500" />
              )}
            </button>
          );
        })}
      </div>

      {/* Section Divider & Day Status Header */}
      <div className="mt-5 pt-4 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <Sparkles className="w-3.5 h-3.5 text-sky-500" />
          <h4 className="text-xs font-bold text-slate-900 dark:text-white">
            {month + 1}月{selectedDay}日 入库收藏
          </h4>
          <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
            {dayItems.length} 条
          </span>
        </div>

        {onViewAllData && (
          <button
            type="button"
            onClick={() => onViewAllData()}
            className="text-[11px] font-semibold text-sky-600 dark:text-sky-400 hover:underline flex items-center gap-0.5 cursor-pointer"
          >
            全部数据
            <ArrowRight className="w-3 h-3" />
          </button>
        )}
      </div>

      {/* Collection Items List below Calendar, reactive to selected day */}
      <div className="mt-3 space-y-2.5 max-h-[380px] overflow-y-auto pr-1">
        {dayItems.length > 0 ? (
          <>
          {visibleItems.map((item) => {
            const platformMeta = PLATFORMS.find((p) => p.id === item.platform) || PLATFORMS[0];
            const displayTime = item.crawlTime ? item.crawlTime.split(' ')[1] : '';

            return (
              <div
                key={item.id}
                onClick={() => onSelectItem?.(item)}
                className="group p-2.5 rounded-2xl border border-slate-100 dark:border-slate-800 hover:border-slate-200 dark:hover:border-slate-700 bg-slate-50/50 dark:bg-slate-800/30 hover:bg-slate-50 dark:hover:bg-slate-800/60 transition-all flex gap-3 cursor-pointer"
              >
                {/* Thumbnail */}
                <div className="relative w-20 h-14 rounded-xl overflow-hidden bg-slate-200 dark:bg-slate-700 shrink-0">
                  {item.coverUrl ? (
                    <img
                      src={item.coverUrl}
                      alt={item.title}
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                      referrerPolicy="no-referrer"
                    />
                  ) : null}
                  {item.duration && (
                    <span className="absolute bottom-1 right-1 px-1.5 py-0.2 rounded bg-black/75 text-white text-[9px] font-mono">
                      {item.duration}
                    </span>
                  )}
                  <span className={`absolute top-1 left-1 px-1.5 py-0.2 rounded text-[9px] font-bold border backdrop-blur-xs ${platformMeta.badgeBg}`}>
                    {platformMeta.name.split(' ')[0]}
                  </span>
                </div>

                {/* Content Details */}
                <div className="flex-1 min-w-0 flex flex-col justify-between">
                  <div>
                    <h5
                      className="text-xs font-bold text-slate-800 dark:text-slate-100 line-clamp-2 leading-tight group-hover:text-sky-600 dark:group-hover:text-sky-400 transition-colors"
                      title={item.title}
                    >
                      {item.title}
                    </h5>
                  </div>

                  <div className="flex items-center justify-between mt-1 text-[11px] text-slate-400 dark:text-slate-400">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span className="truncate max-w-[85px] font-medium text-slate-600 dark:text-slate-300">
                        {item.author}
                      </span>
                      {displayTime && (
                        <span className="text-[10px] text-slate-400 flex items-center gap-0.5">
                          <Clock className="w-2.5 h-2.5" />
                          {displayTime}
                        </span>
                      )}
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      {item.folderName && (
                        <span className="text-[10px] px-1.5 py-0.2 rounded bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 border border-slate-200/60 dark:border-slate-700 flex items-center gap-1 truncate max-w-[90px]">
                          <Folder className="w-2.5 h-2.5 text-slate-400" />
                          {item.folderName}
                        </span>
                      )}

                      {item.url && item.url !== '#' && (
                        <a
                          href={item.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="p-1 rounded text-slate-400 hover:text-sky-600 dark:hover:text-sky-400 hover:bg-sky-50 dark:hover:bg-slate-700 transition-colors"
                          title="查看原帖"
                        >
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}

          {/* 超出上限：一键跳转收藏数据中心（按当前选中日期过滤） */}
          {hiddenCount > 0 && (
            <button
              type="button"
              onClick={() => onViewAllData?.(selectedDateStr)}
              className="w-full py-2.5 rounded-2xl border border-sky-100 dark:border-sky-900/60 bg-sky-50/60 dark:bg-sky-950/40 text-sky-600 dark:text-sky-400 hover:bg-sky-100/80 dark:hover:bg-sky-900/50 text-[11px] font-bold flex items-center justify-center gap-1.5 transition-colors cursor-pointer"
            >
              已展示前 {MAX_VISIBLE_ITEMS} 条，查看全部 {dayItems.length} 条
              <ArrowRight className="w-3 h-3" />
            </button>
          )}
          </>
        ) : (
          <div className="py-8 px-4 text-center bg-slate-50/50 dark:bg-slate-800/30 rounded-2xl border border-dashed border-slate-200 dark:border-slate-800">
            <div className="w-9 h-9 mx-auto rounded-full bg-slate-100 dark:bg-slate-800 text-slate-400 flex items-center justify-center mb-2">
              <Inbox className="w-4 h-4" />
            </div>
            <p className="text-xs font-semibold text-slate-600 dark:text-slate-300">
              {month + 1}月{selectedDay}日 暂无抓取记录
            </p>
            <p className="text-[11px] text-slate-400 mt-0.5">
              点击上方带有小蓝点的日期查看当天入库的收藏
            </p>
          </div>
        )}
      </div>
    </div>
  );
};
