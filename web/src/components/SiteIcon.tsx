import React from 'react';

// 素材来源 assets/site_icons，构建时由 web/public/site_icons 提供
const SITE_ICONS: Record<string, string> = {
  bilibili: '/site_icons/bilibili.ico',
  douyin: '/site_icons/douyin.ico',
  kuaishou: '/site_icons/kuaishou.ico',
  weibo: '/site_icons/weibo.ico',
  xiaohongshu: '/site_icons/xiaohongshu.ico',
};

interface SiteIconProps {
  platform: string;
  src?: string;
  name?: string;
  className?: string;
}

/** 平台站点图标：优先后端 icon_url，其次本地映射，均未收录则回退首字母占位 */
export const SiteIcon: React.FC<SiteIconProps> = ({ platform, src, name, className = 'w-4 h-4' }) => {
  const url = src || SITE_ICONS[platform];
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
