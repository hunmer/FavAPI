import React, { useCallback, useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import {
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  Heart,
  Info,
  Loader2,
  MessageCircle,
  Music,
  Play,
  Share2,
  Star,
  X,
} from 'lucide-react';
import * as api from '../../api';
import { FollowItemActionButtons, FollowItemRef, FollowToast } from './FollowItemActions';

interface PlayerModalProps {
  awemeId: string;
  accountId: string;
  /** 作品平台（构造原站链接，用于右栏操作按钮；缺省时链接类操作禁用） */
  platform?: string;
  /** 卡片上的标题（详情加载前占位展示） */
  fallbackTitle?: string;
  onClose: () => void;
  /** 标记已读成功后回调（父视图更新未读点/计数） */
  onRead?: (contentId: string) => void;
  showToast?: FollowToast;
}

/** 图文/视频通用计数格式 */
const fmtCount = (n?: number | null) => {
  if (n == null) return '—';
  if (n >= 10000) return `${(n / 10000).toFixed(1)}w`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
};

/** 格式化时长：douyin 为毫秒 / bilibili 为秒，按数量级归一到秒 → m:ss */
const fmtDur = (ms?: number | null) => {
  if (!ms || ms <= 0) return '';
  const s = Math.round(ms > 10000 ? ms / 1000 : ms);
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, '0')}`;
};

/** 右侧栏 tab 定义（首个为作品信息，后续可扩展） */
const TABS = [
  { id: 'info', label: '信息', icon: Info },
] as const;
type TabId = (typeof TABS)[number]['id'];

/** 特别关注作品播放器：按 aweme_id 调详情接口播放视频/图文，打开即标记已读。 */
export const PlayerModal: React.FC<PlayerModalProps> = ({
  awemeId,
  accountId,
  platform,
  fallbackTitle,
  onClose,
  onRead,
  showToast,
}) => {
  const [info, setInfo] = useState<api.PlayInfo | null>(null);
  const [error, setError] = useState('');
  const [imgIdx, setImgIdx] = useState(0);
  const [tab, setTab] = useState<TabId>('info');

  useEffect(() => {
    let alive = true;
    setInfo(null);
    setError('');
    setImgIdx(0);
    api.fetchPlayInfo(awemeId, accountId)
      .then(async (data) => {
        if (!alive) return;
        setInfo(data);
        // 打开即标记已读（失败静默，不影响播放）
        try {
          await api.markFollowRead(awemeId);
          onRead?.(awemeId);
        } catch { /* ignore */ }
      })
      .catch((e) => alive && setError(e.message || '作品信息获取失败'));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [awemeId, accountId]);

  // Esc 关闭
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      if (e.key === 'ArrowLeft') setImgIdx((i) => Math.max(0, i - 1));
      if (e.key === 'ArrowRight') setImgIdx((i) => Math.min((info?.images.length || 1) - 1, i + 1));
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, info]);

  const stats = info?.statistics || {};
  const images = info?.images || [];
  const isNote = images.length > 0;

  const prevImg = useCallback(() => setImgIdx((i) => Math.max(0, i - 1)), []);
  const nextImg = useCallback(
    () => setImgIdx((i) => Math.min(images.length - 1, i + 1)),
    [images.length]
  );

  const metaRows = info
    ? [
        { label: '作者', value: info.author.nickname ? `@${info.author.nickname}` : '—' },
        {
          label: '发布时间',
          value: info.create_time
            ? new Date(info.create_time * 1000).toLocaleString('zh-CN', { hour12: false })
            : '—',
        },
        { label: '类型', value: isNote ? `图文 · ${images.length} 张` : '视频' },
        ...(fmtDur(info.duration) ? [{ label: '时长', value: fmtDur(info.duration) }] : []),
        { label: '作品 ID', value: info.aweme_id },
      ]
    : [];

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 bg-black/50 dark:bg-black/80 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onClose}
    >
      <motion.div
        initial={{ scale: 0.94, y: 16 }}
        animate={{ scale: 1, y: 0 }}
        exit={{ scale: 0.94, y: 16 }}
        transition={{ type: 'spring', stiffness: 320, damping: 30 }}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-6xl max-h-[92vh] bg-white dark:bg-[#0F1117] rounded-3xl border border-slate-200 dark:border-slate-800 shadow-2xl overflow-hidden flex flex-col"
      >
        {/* 顶栏：标题 + 关闭 */}
        <div className="flex items-start justify-between gap-3 px-5 py-3.5 border-b border-slate-100 dark:border-slate-800/80 shrink-0">
          <div className="min-w-0">
            <p className="text-sm font-bold text-slate-900 dark:text-white truncate">
              {info?.desc?.split('\n')[0] || info?.desc || fallbackTitle || `作品 ${awemeId}`}
            </p>
            {info?.author?.nickname && (
              <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">@{info.author.nickname}</p>
            )}
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-full bg-slate-100 dark:bg-slate-800/80 text-slate-500 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white hover:bg-slate-200 dark:hover:bg-slate-700 flex items-center justify-center shrink-0 transition-colors cursor-pointer"
            aria-label="关闭"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* 主体：左播放区 + 右侧信息栏 */}
        <div className="flex-1 min-h-0 flex">
          {/* 播放区 */}
          <div className="flex-1 min-w-0 flex items-center justify-center bg-slate-100 dark:bg-black/40 p-3 relative">
            {error ? (
              <div className="flex flex-col items-center gap-2 py-16 text-slate-500 dark:text-slate-400">
                <AlertCircle className="w-10 h-10 text-rose-500" />
                <p className="text-xs">{error}</p>
              </div>
            ) : !info ? (
              <div className="flex flex-col items-center gap-2 py-16 text-slate-500 dark:text-slate-400">
                <Loader2 className="w-8 h-8 animate-spin" />
                <p className="text-xs">正在获取作品信息…</p>
              </div>
            ) : isNote ? (
              /* 图文：单页轮播（键盘 ←/→ 切换） */
              <div className="relative w-full h-[62vh] flex items-center justify-center">
                <AnimatePresence mode="wait" initial={false}>
                  <motion.img
                    key={imgIdx}
                    initial={{ opacity: 0, scale: 0.98 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.18 }}
                    src={api.mediaUrl(images[imgIdx].url)}
                    alt={`图片 ${imgIdx + 1}/${images.length}`}
                    className="max-w-full max-h-full object-contain rounded-xl select-none"
                    draggable={false}
                  />
                </AnimatePresence>
                {images.length > 1 && (
                  <>
                    <button
                      onClick={prevImg}
                      disabled={imgIdx === 0}
                      className="absolute left-2 w-9 h-9 rounded-full bg-black/55 text-white flex items-center justify-center hover:bg-black/75 disabled:opacity-25 transition-all cursor-pointer"
                      aria-label="上一张"
                    >
                      <ChevronLeft className="w-5 h-5" />
                    </button>
                    <button
                      onClick={nextImg}
                      disabled={imgIdx === images.length - 1}
                      className="absolute right-2 w-9 h-9 rounded-full bg-black/55 text-white flex items-center justify-center hover:bg-black/75 disabled:opacity-25 transition-all cursor-pointer"
                      aria-label="下一张"
                    >
                      <ChevronRight className="w-5 h-5" />
                    </button>
                    <span className="absolute bottom-3 px-2.5 py-1 rounded-full bg-black/60 text-white text-[11px] font-mono">
                      {imgIdx + 1} / {images.length}
                    </span>
                  </>
                )}
              </div>
            ) : info.iframe_url ? (
              /* 平台官方嵌入播放（YouTube：直链绑定会话不可独立访问） */
              <iframe
                key={info.aweme_id}
                src={info.iframe_url}
                title={info.desc || `作品 ${info.aweme_id}`}
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
                className="w-full aspect-video max-h-[70vh] rounded-xl bg-black"
              />
            ) : (
              /* 视频：直链经后端代理播放（支持拖动进度） */
              <video
                key={info.aweme_id}
                src={api.mediaUrl(info.video_urls[0])}
                controls
                autoPlay
                className="max-w-full max-h-[70vh] rounded-xl bg-black"
              />
            )}
            {/* 图文 BGM：详情接口的 music.play_url（浏览器自动播放策略下需手动点播放） */}
            {info && isNote && info.music_url && (
              <div className="absolute bottom-3 left-3 right-16 flex items-center gap-2 px-3 py-2 rounded-xl bg-black/60 backdrop-blur-sm">
                <Music className="w-3.5 h-3.5 text-sky-400 shrink-0" />
                <audio
                  src={api.mediaUrl(info.music_url)}
                  controls
                  loop
                  className="h-8 w-full max-w-md"
                  title="背景音乐"
                />
              </div>
            )}
          </div>

          {/* 右侧栏：tabs */}
          <aside className="w-72 shrink-0 border-l border-slate-100 dark:border-slate-800/80 flex flex-col min-h-0">
            <div className="flex items-center gap-1 px-3 pt-3 shrink-0">
              {TABS.map(({ id, label, icon: Icon }) => (
                <button
                  key={id}
                  onClick={() => setTab(id)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors cursor-pointer ${
                    tab === id
                      ? 'bg-slate-100 dark:bg-slate-800 text-slate-900 dark:text-white'
                      : 'text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  {label}
                </button>
              ))}
            </div>

            <div className="flex-1 min-h-0 overflow-y-auto p-4">
              {tab === 'info' &&
                (!info ? (
                  <p className="text-xs text-slate-500 py-8 text-center">
                    {error || '正在获取作品信息…'}
                  </p>
                ) : (
                  <div className="space-y-4">
                    {/* 统计 */}
                    <div className="grid grid-cols-2 gap-2">
                      {[
                        { icon: Heart, cls: 'text-rose-500', label: '点赞', value: fmtCount(stats.digg_count) },
                        { icon: MessageCircle, cls: 'text-sky-500', label: '评论', value: fmtCount(stats.comment_count) },
                        { icon: Star, cls: 'text-amber-500', label: '收藏', value: fmtCount(stats.collect_count) },
                        { icon: Share2, cls: 'text-emerald-500', label: '分享', value: fmtCount(stats.share_count) },
                      ].map(({ icon: Icon, cls, label, value }) => (
                        <div key={label} className="rounded-xl bg-slate-100 dark:bg-slate-800/40 px-3 py-2.5 flex items-center gap-2.5">
                          <Icon className={`w-4 h-4 shrink-0 ${cls}`} />
                          <div className="min-w-0">
                            <p className="text-sm font-bold text-slate-900 dark:text-white leading-none">{value}</p>
                            <p className="text-[10px] text-slate-500 dark:text-slate-500 mt-1">{label}</p>
                          </div>
                        </div>
                      ))}
                    </div>

                    {/* 操作按钮 */}
                    <FollowItemActionButtons
                      item={{
                        platform: platform || '',
                        contentId: info.aweme_id,
                        title: info.desc?.split('\n')[0] || fallbackTitle,
                        accountId,
                        url: info.share_url,
                      }}
                      showToast={showToast}
                    />

                    {/* 元数据 */}
                    <div className="space-y-2.5">
                      {metaRows.map(({ label, value }) => (
                        <div key={label} className="flex items-start gap-2 text-xs">
                          <span className="text-slate-500 shrink-0">{label}</span>
                          <span className="text-slate-700 dark:text-slate-300 break-all min-w-0">{value}</span>
                        </div>
                      ))}
                    </div>

                    {/* 完整文案 */}
                    {info.desc && (
                      <div className="space-y-1.5">
                        <p className="text-[11px] font-semibold text-slate-500">文案</p>
                        <p className="text-xs text-slate-700 dark:text-slate-300 whitespace-pre-wrap break-words leading-relaxed">
                          {info.desc}
                        </p>
                      </div>
                    )}

                    {!isNote && (
                      <p className="flex items-center gap-1.5 text-[11px] text-slate-500">
                        <Play className="w-3 h-3" />已标记已读
                      </p>
                    )}
                  </div>
                ))}
            </div>
          </aside>
        </div>
      </motion.div>
    </motion.div>
  );
};
