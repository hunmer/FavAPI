import React, { useEffect, useRef, useState } from 'react';
import { CheckCircle2, Download, ExternalLink, Link2, UserRound } from 'lucide-react';
import { useDismiss } from '../../hooks/useDismiss';
import { DownloadConfirmModal } from '../Data/DownloadConfirmModal';
import * as api from '../../api';

/** 作品原站链接模板（与后端 data_store._CONTENT_URL_TEMPLATES 一致；
 *  tiktok/threads/instagram 的 content_id 无法独立成链，由详情接口下发 share_url） */
const URL_TEMPLATES: Record<string, string> = {
  douyin: 'https://www.douyin.com/video/{id}',
  bilibili: 'https://www.bilibili.com/video/{id}',
  xiaohongshu: 'https://www.xiaohongshu.com/explore/{id}',
  kuaishou: 'https://www.kuaishou.com/short-video/{id}',
  // follows 的 youtube 作品是频道单视频（videoId），非收藏的播放列表
  youtube: 'https://www.youtube.com/watch?v={id}',
};

export const followItemUrl = (platform: string, contentId: string) =>
  (URL_TEMPLATES[platform] || '').replace('{id}', contentId);

/** 作品原站链接：详情下发的 share_url 优先（模板拼不出的平台），否则按平台模板拼 */
const resolveItemUrl = (item: FollowItemRef) =>
  item.url || followItemUrl(item.platform, item.contentId);

/** 右键菜单/操作按钮共用的作品引用 */
export interface FollowItemRef {
  platform: string;
  contentId: string;
  title?: string | null;
  /** 浏览/下载所经账号（账号打开、下载入队） */
  accountId: string;
  /** 详情接口下发的原站链接（tiktok/threads/instagram 等） */
  url?: string | null;
  /** 当前已读状态（右键菜单的已读切换文案用） */
  read?: boolean;
}

export type FollowToast = (msg: string, type?: 'success' | 'info' | 'error') => void;

// ---------- 基础动作（与 DataBrowserView 的卡片菜单动作同款语义） ----------

const openExternal = (url: string, showToast?: FollowToast) => {
  // window.open 被弹窗拦截器拦截时静默返回 null，需明确提示
  if (!window.open(url, '_blank', 'noopener,noreferrer')) {
    showToast?.('新窗口被浏览器拦截，请允许本站弹窗后重试', 'error');
  }
};

const copyUrl = async (url: string, showToast?: FollowToast) => {
  try {
    await navigator.clipboard.writeText(url);
    showToast?.('已复制链接地址');
  } catch {
    showToast?.('复制失败，请手动复制', 'error');
  }
};

/** 账号打开：用浏览账号的隔离浏览器（session）打开原站链接 */
const openWithAccount = async (item: FollowItemRef, url: string, showToast?: FollowToast) => {
  try {
    const res = await api.toggleBrowse(item.accountId, url);
    showToast?.(
      res.tab
        ? '已在登录/抓取占用的浏览器中新开标签页'
        : res.navigated
          ? '已在打开的账号浏览器中跳转'
          : '已通过账号隔离浏览器打开'
    );
  } catch (err: any) {
    showToast?.(err?.message || '账号浏览器打开失败', 'error');
  }
};

/** 已读切换：调 API 成功后回调父视图更新列表（item.read 为切换前状态） */
const toggleRead = async (
  item: FollowItemRef,
  onReadChange: (contentId: string, read: boolean) => void,
  showToast?: FollowToast
) => {
  const target = !item.read;
  try {
    await (target ? api.markFollowRead(item.contentId) : api.unmarkFollowRead(item.contentId));
    onReadChange(item.contentId, target);
    showToast?.(target ? '已标记为已读' : '已标记为未读', 'info');
  } catch (err: any) {
    showToast?.(err?.message || '已读状态更新失败', 'error');
  }
};

// ---------- 下载动作：点击 → 下载确认弹窗 → createDownload 入队 ----------

/** 平台下载能力/默认清晰度（模块级缓存，多处操作不重复拉取） */
let _dlSettings: Promise<{ platforms: Set<string>; quality: string }> | null = null;
const dlSettings = () =>
  (_dlSettings ??= Promise.all([
    api.fetchPlatformDownloadSet(),
    api.fetchAppSettings().catch(() => null),
  ]).then(([platforms, s]) => ({ platforms, quality: s?.download_quality || 'auto' })));

/** 下载触发按钮：样式由调用方给（菜单项 / 卡片按钮），内部管理确认弹窗 */
const DownloadTrigger: React.FC<{
  item: FollowItemRef;
  url: string;
  showToast?: FollowToast;
  className: string;
}> = ({ item, url, showToast, className }) => {
  const [confirm, setConfirm] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [platformDownload, setPlatformDownload] = useState(false);
  const [defaultQuality, setDefaultQuality] = useState('auto');
  useEffect(() => {
    dlSettings().then((s) => {
      setPlatformDownload(s.platforms.has(item.platform));
      setDefaultQuality(s.quality);
    });
  }, [item.platform]);

  const submit = async (downloader: api.DownloaderId, quality: string) => {
    if (submitting) return;
    setSubmitting(true);
    try {
      await api.createDownload({
        content_id: item.contentId,
        platform: item.platform,
        account_id: item.accountId || '',
        title: item.title || undefined,
        url,
        downloader,
        quality,
      });
      showToast?.('已加入下载队列，进度见「下载队列」页');
      setConfirm(false);
    } catch (err: any) {
      showToast?.(err?.message || '下载任务创建失败', 'error');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <button type="button" disabled={!url} onClick={() => setConfirm(true)} className={className}>
        <Download className="w-3.5 h-3.5 shrink-0" />
        下载视频
      </button>
      {confirm && (
        <DownloadConfirmModal
          singleTitle={item.title || undefined}
          count={1}
          platformDownload={platformDownload}
          defaultQuality={defaultQuality}
          confirming={submitting}
          onConfirm={submit}
          onClose={() => !submitting && setConfirm(false)}
        />
      )}
    </>
  );
};

// ---------- 右键菜单（AuthorPage 卡片用） ----------

const MenuItem: React.FC<{
  label: string;
  disabled?: boolean;
  onClick: () => void;
  children?: React.ReactNode;
}> = ({ label, disabled, onClick, children }) => (
  <button
    type="button"
    disabled={disabled}
    onClick={onClick}
    className={`w-full px-3 py-1.5 text-left text-xs font-semibold flex items-center gap-2 transition-colors ${
      disabled
        ? 'opacity-40 cursor-not-allowed'
        : 'text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-white cursor-pointer'
    }`}
  >
    {children}
    {label}
  </button>
);

/** 特别关注作品卡片右键菜单（样式与 Data 模块 ItemActionMenu 一致） */
export const FollowItemActionMenu: React.FC<{
  item: FollowItemRef;
  /** 弹出锚点（fixed 坐标），自动防止溢出屏幕 */
  x: number;
  y: number;
  onClose: () => void;
  /** 已读切换成功回调（父视图更新列表未读点） */
  onReadChange?: (contentId: string, read: boolean) => void;
  showToast?: FollowToast;
}> = ({ item, x, y, onClose, onReadChange, showToast }) => {
  // 点击其他区域 / 右键 / 滚动 / 缩放时关闭（浮层内部点击由菜单项 onClick 自行关闭）
  const rootRef = useRef<HTMLDivElement>(null);
  useDismiss(onClose, true, rootRef);

  const url = resolveItemUrl(item);
  const hasUrl = !!url;
  const act = (fn: () => void) => {
    onClose();
    fn();
  };

  return (
    <div
      ref={rootRef}
      className="fixed z-[60] py-1 w-40 rounded-xl bg-white dark:bg-[#161B26] border border-slate-200 dark:border-slate-700 shadow-lg overflow-hidden anim-modal-enter"
      style={{
        left: Math.max(8, Math.min(x, window.innerWidth - 168)),
        top: Math.min(y, window.innerHeight - 230),
      }}
      onClick={(e) => e.stopPropagation()}
      onContextMenu={(e) => e.preventDefault()}
    >
      <MenuItem label="新窗口打开" disabled={!hasUrl} onClick={() => act(() => openExternal(url, showToast))}>
        <ExternalLink className="w-3.5 h-3.5 shrink-0" />
      </MenuItem>
      <MenuItem label="复制URL" disabled={!hasUrl} onClick={() => act(() => copyUrl(url, showToast))}>
        <Link2 className="w-3.5 h-3.5 shrink-0" />
      </MenuItem>
      <MenuItem label="账号打开" disabled={!hasUrl} onClick={() => act(() => openWithAccount(item, url, showToast))}>
        <UserRound className="w-3.5 h-3.5 shrink-0" />
      </MenuItem>
      {/* 下载不关菜单：确认弹窗（z-70）盖在其上，取消后菜单仍可继续操作 */}
      <DownloadTrigger
        item={item}
        url={url}
        showToast={showToast}
        className="w-full px-3 py-1.5 text-left text-xs font-semibold flex items-center gap-2 transition-colors text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-white cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
      />
      {onReadChange && (
        <>
          <div className="my-1 border-t border-slate-100 dark:border-slate-800" />
          <MenuItem
            label={item.read ? '标记未读' : '标记已读'}
            disabled={item.read == null}
            onClick={() => act(() => toggleRead(item, onReadChange, showToast))}
          >
            <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
          </MenuItem>
        </>
      )}
    </div>
  );
};

// ---------- 操作按钮列表（PlayerModal 信息 tab 用） ----------

/** 作品操作按钮 2x2 网格：新窗口打开 / 复制URL / 账号打开 / 下载视频 */
export const FollowItemActionButtons: React.FC<{
  item: FollowItemRef;
  showToast?: FollowToast;
}> = ({ item, showToast }) => {
  const url = resolveItemUrl(item);
  const btn =
    'flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold bg-slate-100 dark:bg-slate-800/40 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-white transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed';
  return (
    <div className="grid grid-cols-2 gap-2">
      <button type="button" className={btn} disabled={!url} onClick={() => openExternal(url, showToast)}>
        <ExternalLink className="w-3.5 h-3.5" />新窗口打开
      </button>
      <button type="button" className={btn} disabled={!url} onClick={() => copyUrl(url, showToast)}>
        <Link2 className="w-3.5 h-3.5" />复制URL
      </button>
      <button type="button" className={btn} disabled={!url} onClick={() => openWithAccount(item, url, showToast)}>
        <UserRound className="w-3.5 h-3.5" />账号打开
      </button>
      <DownloadTrigger item={item} url={url} showToast={showToast} className={btn} />
    </div>
  );
};
