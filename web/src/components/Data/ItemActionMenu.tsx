import React from 'react';
import { ScrapedItem } from '../../types';
import { ExternalLink, Link2, Trash2, UserRound } from 'lucide-react';
import { useDismiss } from '../../hooks/useDismiss';

/** 收藏卡片/列表行共用的操作菜单项 */
const MenuItem: React.FC<{
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  danger?: boolean;
  disabled?: boolean;
  onClick: () => void;
}> = ({ icon: Icon, label, danger, disabled, onClick }) => (
  <button
    type="button"
    disabled={disabled}
    onClick={onClick}
    className={`w-full px-3 py-1.5 text-left text-xs font-semibold flex items-center gap-2 transition-colors ${
      disabled
        ? 'opacity-40 cursor-not-allowed'
        : danger
          ? 'text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950 cursor-pointer'
          : 'text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-white cursor-pointer'
    }`}
  >
    <Icon className="w-3.5 h-3.5 shrink-0" />
    {label}
  </button>
);

export interface ItemActionMenuProps {
  item: ScrapedItem;
  /** 弹出锚点（fixed 坐标），自动防止溢出屏幕 */
  x: number;
  y: number;
  onClose: () => void;
  onOpenExternal?: (item: ScrapedItem) => void;
  onCopyUrl?: (item: ScrapedItem) => void;
  /** 用该条收藏所属账号的隔离浏览器打开（session 浏览器） */
  onOpenWithAccount?: (item: ScrapedItem) => void;
  onDelete?: (item: ScrapedItem) => void;
}

/** 收藏条目右键/dots 操作菜单（网格卡片与列表行共用）。 */
export const ItemActionMenu: React.FC<ItemActionMenuProps> = ({
  item,
  x,
  y,
  onClose,
  onOpenExternal,
  onCopyUrl,
  onOpenWithAccount,
  onDelete,
}) => {
  // 点击其他区域 / 右键 / 滚动 / 缩放时关闭
  useDismiss(onClose);

  const hasUrl = !!item.url;
  const act = (fn?: (item: ScrapedItem) => void) => {
    onClose();
    fn?.(item);
  };

  return (
    <div
      className="fixed z-[60] py-1 w-40 rounded-xl bg-white dark:bg-[#161B26] border border-slate-200 dark:border-slate-700 shadow-lg overflow-hidden anim-modal-enter"
      style={{
        left: Math.max(8, Math.min(x, window.innerWidth - 168)),
        top: Math.min(y, window.innerHeight - 230),
      }}
      onClick={(e) => e.stopPropagation()}
      onContextMenu={(e) => e.preventDefault()}
    >
      <MenuItem icon={ExternalLink} label="新窗口打开" disabled={!hasUrl} onClick={() => act(onOpenExternal)} />
      <MenuItem icon={Link2} label="复制URL" disabled={!hasUrl} onClick={() => act(onCopyUrl)} />
      <MenuItem icon={UserRound} label="账号打开" disabled={!hasUrl} onClick={() => act(onOpenWithAccount)} />
      <div className="my-1 border-t border-slate-100 dark:border-slate-800" />
      <MenuItem icon={Trash2} label="删除" danger onClick={() => act(onDelete)} />
    </div>
  );
};
