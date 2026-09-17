import React from 'react';
import { ScrapedItem } from '../../types';
import { PLATFORMS } from '../../data/mockFavData';
import { CheckCircle2, ExternalLink, ImageOff, ThumbsUp } from 'lucide-react';
import { SiteIcon, usePlatformInfo } from '../SiteIcon';

interface DataItemCardProps {
  item: ScrapedItem;
  idx: number;
  onSelect: (item: ScrapedItem) => void;
  /** 多选模式：点击卡片切换选中而非打开详情 */
  selectable?: boolean;
  selected?: boolean;
  onToggleSelect?: (item: ScrapedItem) => void;
  /** 点击作者名应用/取消作者过滤 */
  onFilterAuthor?: (author: string) => void;
}

/** 数据浏览网格视图的封面卡片（自 DataBrowserView 抽离）。 */
export const DataItemCard: React.FC<DataItemCardProps> = ({
  item,
  idx,
  onSelect,
  selectable = false,
  selected = false,
  onToggleSelect,
  onFilterAuthor,
}) => {
  // mock 未收录的平台（如 threads）回退到后端 /platforms 的 display_name
  const platformMeta = PLATFORMS.find((p) => p.id === item.platform);
  const backendInfo = usePlatformInfo(item.platform);
  const platformName = platformMeta?.name || backendInfo?.display_name || item.platform;

  return (
    <div
      onClick={() => (selectable ? onToggleSelect?.(item) : onSelect(item))}
      className={`anim-card-enter bg-white rounded-[24px] border shadow-2xs hover:shadow-lg transition-all duration-200 overflow-hidden flex flex-col group cursor-pointer ${
        selected ? 'border-violet-500 ring-2 ring-violet-500/30' : 'border-slate-200/80'
      }`}
      style={{ animationDelay: `${Math.min(idx * 30, 240)}ms` }}
    >
      {/* Cover Image Container with corner badges */}
      <div className="relative aspect-video w-full bg-slate-100 overflow-hidden">
        {item.coverUrl ? (
          <img
            src={item.coverUrl}
            alt={item.title}
            className={`w-full h-full object-cover group-hover:scale-104 transition-transform duration-300 ${selected ? 'opacity-80' : ''}`}
            referrerPolicy="no-referrer"
          />
        ) : (
          <div className="w-full h-full flex flex-col items-center justify-center gap-1.5 text-slate-300">
            <ImageOff className="w-8 h-8" />
            <span className="text-[11px] font-medium">暂无封面</span>
          </div>
        )}
        {/* Gradient bottom overlay */}
        <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-transparent to-black/20 pointer-events-none" />

        {/* 多选模式：左上角选中标记（取代平台角标位置） */}
        {selectable ? (
          <div className="absolute top-2.5 left-2.5">
            <span
              className={`w-6 h-6 rounded-full flex items-center justify-center border-2 transition-all ${
                selected
                  ? 'bg-violet-600 border-violet-600 text-white shadow-sm'
                  : 'bg-black/35 border-white/85 text-transparent backdrop-blur-xs'
              }`}
            >
              <CheckCircle2 className="w-4 h-4" />
            </span>
          </div>
        ) : (
          /* Top-left: Platform badge */
          <div className="absolute top-2.5 left-2.5">
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-bold bg-black/60 text-white backdrop-blur-xs">
              <SiteIcon platform={item.platform} name={platformName} className="w-3 h-3" />
              {platformName.split(' ')[0]}
            </span>
          </div>
        )}

        {/* Top-right: Folder name */}
        <div className="absolute top-2.5 right-2.5">
          <span className="px-2 py-0.5 rounded-md text-[10px] font-medium bg-black/60 text-white/90 backdrop-blur-xs truncate max-w-[120px] block">
            {item.folderName}
          </span>
        </div>

        {/* Bottom metrics on cover: Duration & Likes/Views */}
        <div className="absolute bottom-2 left-2.5 right-2.5 flex items-center justify-between text-white text-[11px] font-semibold">
          <span className="flex items-center gap-1 drop-shadow-xs">
            <ThumbsUp className="w-3 h-3 text-white/80" />
            {(item.likes / 1000).toFixed(1)}k
          </span>
          {item.duration && (
            <span className="px-1.5 py-0.5 rounded bg-black/65 font-mono text-[10px]">
              {item.duration}
            </span>
          )}
        </div>
      </div>

      {/* Card Body */}
      <div className="p-4 flex flex-col justify-between flex-1 space-y-3">
        <h4 className="text-xs sm:text-sm font-bold text-slate-900 line-clamp-2 leading-snug group-hover:text-indigo-600 transition-colors">
          {item.title}
        </h4>

        <div className="space-y-2 pt-1 border-t border-slate-100">
          <div className="flex items-center justify-between text-xs text-slate-600">
            <div className="flex items-center gap-1.5 min-w-0">
              {item.authorAvatar && (
                <img
                  src={item.authorAvatar}
                  alt=""
                  className="w-4 h-4 rounded-full object-cover shrink-0"
                  referrerPolicy="no-referrer"
                />
              )}
              <span
                onClick={(e) => {
                  e.stopPropagation();
                  onFilterAuthor?.(item.author);
                }}
                title="点击按该作者过滤"
                className="truncate font-medium cursor-pointer hover:text-indigo-600 transition-colors"
              >
                {item.author}
              </span>
            </div>
            <span className="text-[11px] text-slate-400 shrink-0">
              {item.favTime.split(' ')[0]}
            </span>
          </div>

          <div className="flex items-center justify-between text-[11px] text-slate-400">
            <span className="truncate">{item.accountName}</span>
            {item.url ? <a
              href={item.url}
              target="_blank"
              rel="noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="text-indigo-600 hover:text-indigo-800 inline-flex items-center gap-0.5 font-semibold"
            >
              原站 <ExternalLink className="w-3 h-3" />
            </a> : <span className="text-slate-400">无链接</span>}
          </div>
        </div>
      </div>
    </div>
  );
};
