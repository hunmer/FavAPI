import React from 'react';
import { ScrapedItem } from '../../types';
import { PLATFORMS } from '../../data/platforms';
import { Heart, Star, ExternalLink, Folder } from 'lucide-react';

interface RecentCollectionCardProps {
  item: ScrapedItem;
  onOpenDetail?: (item: ScrapedItem) => void;
}

export const RecentCollectionCard: React.FC<RecentCollectionCardProps> = ({
  item,
  onOpenDetail,
}) => {
  const platformMeta = PLATFORMS.find((p) => p.id === item.platform) || PLATFORMS[0];

  return (
    <div className="bg-white dark:bg-[#161B26] rounded-3xl p-4 border border-slate-100 dark:border-slate-800 shadow-sm hover:shadow-md dark:hover:shadow-slate-950/40 transition-all flex flex-col justify-between group">
      <div>
        {/* Cover Image Container */}
        <div className="relative aspect-video rounded-2xl overflow-hidden bg-slate-100 dark:bg-slate-800 mb-3.5">
          <img
            src={item.coverUrl}
            alt={item.title}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
          />

          {/* Duration Badge */}
          {item.duration && (
            <span className="absolute bottom-2 right-2 px-2 py-0.5 rounded-lg bg-black/75 text-white text-[10px] font-mono font-semibold backdrop-blur-sm">
              {item.duration}
            </span>
          )}

          {/* Platform Tag */}
          <span
            className={`absolute top-2 left-2 px-2 py-0.5 rounded-lg text-[10px] font-bold border backdrop-blur-sm ${platformMeta.badgeBg}`}
          >
            {platformMeta.name.split(' ')[0]}
          </span>
        </div>

        {/* Title */}
        <h4 
          onClick={() => onOpenDetail?.(item)}
          className="text-sm font-bold text-slate-900 dark:text-white leading-snug line-clamp-2 cursor-pointer group-hover:text-sky-600 dark:group-hover:text-sky-400 transition-colors"
          title={item.title}
        >
          {item.title}
        </h4>

        {/* Author & Folder info */}
        <div className="flex items-center justify-between mt-2.5 text-xs text-slate-500 dark:text-slate-400">
          <div className="flex items-center gap-1.5 min-w-0">
            {item.authorAvatar && (
              <img
                src={item.authorAvatar}
                alt={item.author}
                className="w-5 h-5 rounded-full object-cover shrink-0"
              />
            )}
            <span className="truncate font-medium text-slate-600 dark:text-slate-300">{item.author}</span>
          </div>

          <span className="text-[11px] px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 font-medium truncate max-w-[110px] flex items-center gap-1">
            <Folder className="w-2.5 h-2.5 text-slate-400" />
            {item.folderName}
          </span>
        </div>
      </div>

      {/* Footer: Likes, Favorites and Original Link */}
      <div className="mt-4 pt-3 border-t border-slate-50 dark:border-slate-800/80 flex items-center justify-between text-xs text-slate-400 dark:text-slate-400">
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1 text-slate-500 dark:text-slate-400 font-medium">
            <Heart className="w-3.5 h-3.5 text-rose-500" />
            {item.likes >= 10000 ? `${(item.likes / 10000).toFixed(1)}万` : item.likes}
          </span>
          <span className="flex items-center gap-1 text-slate-500 dark:text-slate-400 font-medium">
            <Star className="w-3.5 h-3.5 text-amber-500" />
            {item.favorites >= 10000 ? `${(item.favorites / 10000).toFixed(1)}万` : item.favorites}
          </span>
        </div>

        <a
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          className="p-1.5 rounded-lg text-slate-400 dark:text-slate-400 hover:text-sky-600 dark:hover:text-sky-400 hover:bg-sky-50 dark:hover:bg-sky-950/40 transition-colors flex items-center gap-1 text-[11px] font-semibold"
          title="前往原站查看"
        >
          <span>查看原帖</span>
          <ExternalLink className="w-3 h-3" />
        </a>
      </div>
    </div>
  );
};
