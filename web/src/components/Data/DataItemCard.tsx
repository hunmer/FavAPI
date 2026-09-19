import React, { useState } from 'react';
import { ScrapedItem } from '../../types';
import { PLATFORMS } from '../../data/mockFavData';
import { coverApiUrl } from '../../api';
import { CheckCircle2, ExternalLink, ImageOff, MoreVertical, ThumbsUp } from 'lucide-react';
import { SiteIcon, usePlatformInfo } from '../SiteIcon';
import { ItemActionMenu } from './ItemActionMenu';

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
  /** 卡片右键/dots 菜单动作（由父视图统一处理） */
  onOpenExternal?: (item: ScrapedItem) => void;
  onCopyUrl?: (item: ScrapedItem) => void;
  /** 用该条收藏所属账号的隔离浏览器打开（session 浏览器） */
  onOpenWithAccount?: (item: ScrapedItem) => void;
  /** 加入下载队列（默认 yt-dlp） */
  onDownload?: (item: ScrapedItem) => void;
  onDelete?: (item: ScrapedItem) => void;
  /** 瀑布流视图：封面按图片原始宽高比呈现（默认固定 16:9） */
  variableRatio?: boolean;
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
  onOpenExternal,
  onCopyUrl,
  onOpenWithAccount,
  onDownload,
  onDelete,
  variableRatio = false,
}) => {
  // mock 未收录的平台（如 threads）回退到后端 /platforms 的 display_name
  const platformMeta = PLATFORMS.find((p) => p.id === item.platform);
  const backendInfo = usePlatformInfo(item.platform);
  const platformName = platformMeta?.name || backendInfo?.display_name || item.platform;

  // 瀑布流：封面加载后按原始宽高比撑开，未加载前占位 3:4 防止布局抖动
  const [coverRatio, setCoverRatio] = useState(3 / 4);

  // 右键 / dots 共用的操作菜单（fixed 定位，menu.x/y 为弹出的锚点坐标）
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null);

  return (
    <div
      onClick={() => (selectable ? onToggleSelect?.(item) : onSelect(item))}
      onContextMenu={(e) => {
        e.preventDefault();
        e.stopPropagation();
        setMenu({ x: e.clientX, y: e.clientY });
      }}
      className={`anim-card-enter bg-white dark:bg-[#161B26] rounded-[24px] border shadow-2xs hover:shadow-lg dark:hover:shadow-slate-950/40 transition-all duration-200 overflow-hidden flex flex-col group cursor-pointer ${
        selected
          ? 'border-violet-500 ring-2 ring-violet-500/30'
          : 'border-slate-200/80 dark:border-slate-800'
      }`}
      style={{ animationDelay: `${Math.min(idx * 30, 240)}ms` }}
    >
      {/* Cover Image Container with corner badges */}
      <div
        className={`relative w-full bg-slate-100 dark:bg-slate-800 overflow-hidden ${variableRatio ? '' : 'aspect-video'}`}
        style={variableRatio ? { aspectRatio: String(coverRatio) } : undefined}
      >
        {item.coverUrl ? (
          <img
            /* 封面统一走后端接口：已本地化回本地文件，未本地化由后端跳转远程原图 */
            src={coverApiUrl(item.platform, item.id)}
            alt={item.title}
            onLoad={(e) => {
              if (!variableRatio) return;
              const { naturalWidth, naturalHeight } = e.currentTarget;
              if (naturalWidth && naturalHeight) setCoverRatio(naturalWidth / naturalHeight);
            }}
            className={`w-full h-full object-cover group-hover:scale-104 transition-transform duration-300 ${selected ? 'opacity-80' : ''}`}
            referrerPolicy="no-referrer"
          />
        ) : (
          <div className="w-full h-full flex flex-col items-center justify-center gap-1.5 text-slate-300 dark:text-slate-600">
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

        {/* Top-right: 入库来源（喜欢/稍后再看/特别关注…；收藏列表为默认来源不显示） */}
        <div className="absolute top-2.5 right-2.5 flex items-center gap-1 max-w-[75%]">
          {item.sourceName && item.sourceName !== '收藏列表' && (
            <span className="px-2 py-0.5 rounded-md text-[10px] font-semibold bg-indigo-600/85 text-white backdrop-blur-xs truncate max-w-[120px] block">
              {item.sourceName}
            </span>
          )}
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
        <h4 className="text-xs sm:text-sm font-bold text-slate-900 dark:text-white line-clamp-2 leading-snug group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors">
          {item.title}
        </h4>

        <div className="space-y-2 pt-1 border-t border-slate-100 dark:border-slate-800">
          <div className="flex items-center justify-between text-xs text-slate-600 dark:text-slate-300">
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
                className="truncate font-medium cursor-pointer hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors"
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
            <div className="flex items-center gap-1 shrink-0">
              {item.url ? (
                <a
                  href={item.url}
                  target="_blank"
                  rel="noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  className="text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 dark:hover:text-indigo-300 inline-flex items-center gap-0.5 font-semibold"
                >
                  原站 <ExternalLink className="w-3 h-3" />
                </a>
              ) : (
                <span>无链接</span>
              )}
              {/* 右下角 dots：弹出与右键一致的操作菜单 */}
              <button
                type="button"
                title="更多操作"
                onClick={(e) => {
                  e.stopPropagation();
                  const rect = e.currentTarget.getBoundingClientRect();
                  setMenu({ x: rect.right - 160, y: rect.bottom + 4 });
                }}
                className="w-6 h-6 rounded-full flex items-center justify-center text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer"
              >
                <MoreVertical className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* 右键 / dots 操作菜单 */}
      {menu && (
        <ItemActionMenu
          item={item}
          x={menu.x}
          y={menu.y}
          onClose={() => setMenu(null)}
          onOpenExternal={onOpenExternal}
          onCopyUrl={onCopyUrl}
          onOpenWithAccount={onOpenWithAccount}
          onDownload={onDownload}
          onDelete={onDelete}
        />
      )}
    </div>
  );
};
