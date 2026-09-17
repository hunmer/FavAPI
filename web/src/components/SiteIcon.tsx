import React, { useEffect, useState } from 'react';
import { listPlatforms, PlatformInfoRow } from '../api';

// 素材来源 assets/site_icons，构建时由 web/public/site_icons 提供
const SITE_ICONS: Record<string, string> = {
  bilibili: '/site_icons/bilibili.ico',
  douyin: '/site_icons/douyin.ico',
  kuaishou: '/site_icons/kuaishou.ico',
  weibo: '/site_icons/weibo.ico',
  xiaohongshu: '/site_icons/xiaohongshu.ico',
  tiktok: '/site_icons/tiktok.ico',
  wechat: '/site_icons/wechat.svg',
};

// 后端平台元信息（display_name / icon_url）缓存：不在 mock PLATFORMS 内的平台（如 threads）由此兜底
let platformInfoCache: Record<string, PlatformInfoRow> | null = null;
let platformInfoPromise: Promise<Record<string, PlatformInfoRow>> | null = null;

function loadPlatformInfos(): Promise<Record<string, PlatformInfoRow>> {
  if (!platformInfoPromise) {
    platformInfoPromise = listPlatforms()
      .then((items) => {
        platformInfoCache = Object.fromEntries(items.map((p) => [p.platform, p]));
        return platformInfoCache;
      })
      .catch(() => ({} as Record<string, PlatformInfoRow>));
  }
  return platformInfoPromise;
}

export function usePlatformInfos(): Record<string, PlatformInfoRow> {
  const [map, setMap] = useState<Record<string, PlatformInfoRow>>(platformInfoCache || {});
  useEffect(() => {
    let alive = true;
    loadPlatformInfos().then((loaded) => {
      if (alive) setMap(loaded);
    });
    return () => {
      alive = false;
    };
  }, []);
  return map;
}

export function usePlatformInfo(platform: string): PlatformInfoRow | undefined {
  return usePlatformInfos()[platform];
}

interface SiteIconProps {
  platform: string;
  src?: string;
  name?: string;
  className?: string;
}

/** 平台站点图标：优先显式 src，其次后端 icon_url 与本地映射，均未收录则回退首字母占位 */
export const SiteIcon: React.FC<SiteIconProps> = ({ platform, src, name, className = 'w-4 h-4' }) => {
  const backend = usePlatformInfo(platform);
  const url = src || backend?.icon_url || SITE_ICONS[platform];
  if (url) {
    return <img src={url} alt={name || platform} className={`rounded-sm object-contain shrink-0 ${className}`} />;
  }
  return (
    <span
      aria-hidden
      className={`inline-flex items-center justify-center rounded-sm bg-slate-100 dark:bg-slate-700 text-slate-500 dark:text-slate-300 font-bold leading-none ${className}`}
    >
      {(name || platform).charAt(0).toUpperCase()}
    </span>
  );
};
