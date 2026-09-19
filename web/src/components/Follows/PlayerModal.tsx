import React, { useCallback, useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import {
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  Heart,
  Loader2,
  MessageCircle,
  Music,
  Play,
  Share2,
  Star,
  X,
} from 'lucide-react';
import * as api from '../../api';

interface PlayerModalProps {
  awemeId: string;
  accountId: string;
  /** 卡片上的标题（详情加载前占位展示） */
  fallbackTitle?: string;
  onClose: () => void;
  /** 标记已读成功后回调（父视图更新未读点/计数） */
  onRead?: (contentId: string) => void;
}

/** 图文/视频通用计数格式 */
const fmtCount = (n?: number | null) => {
  if (n == null) return '—';
  if (n >= 10000) return `${(n / 10000).toFixed(1)}w`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
};

/** 特别关注作品播放器：按 aweme_id 调详情接口播放视频/图文，打开即标记已读。 */
export const PlayerModal: React.FC<PlayerModalProps> = ({
  awemeId,
  accountId,
  fallbackTitle,
  onClose,
  onRead,
}) => {
  const [info, setInfo] = useState<api.PlayInfo | null>(null);
  const [error, setError] = useState('');
  const [imgIdx, setImgIdx] = useState(0);

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

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onClose}
    >
      <motion.div
        initial={{ scale: 0.94, y: 16 }}
        animate={{ scale: 1, y: 0 }}
        exit={{ scale: 0.94, y: 16 }}
        transition={{ type: 'spring', stiffness: 320, damping: 30 }}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-4xl max-h-[92vh] bg-[#0F1117] rounded-3xl border border-slate-800 shadow-2xl overflow-hidden flex flex-col"
      >
        {/* 顶栏：标题 + 关闭 */}
        <div className="flex items-start justify-between gap-3 px-5 py-3.5 border-b border-slate-800/80 shrink-0">
          <div className="min-w-0">
            <p className="text-sm font-bold text-white truncate">
              {info?.desc?.split('\n')[0] || info?.desc || fallbackTitle || `作品 ${awemeId}`}
            </p>
            {info?.author?.nickname && (
              <p className="text-[11px] text-slate-400 mt-0.5">@{info.author.nickname}</p>
            )}
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-full bg-slate-800/80 text-slate-300 hover:text-white hover:bg-slate-700 flex items-center justify-center shrink-0 transition-colors cursor-pointer"
            aria-label="关闭"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* 播放区 */}
        <div className="flex-1 min-h-0 flex items-center justify-center bg-black/40 p-3 relative">
          {error ? (
            <div className="flex flex-col items-center gap-2 py-16 text-slate-400">
              <AlertCircle className="w-10 h-10 text-rose-500" />
              <p className="text-xs">{error}</p>
            </div>
          ) : !info ? (
            <div className="flex flex-col items-center gap-2 py-16 text-slate-400">
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

        {/* 底栏：统计 */}
        {info && (
          <div className="flex items-center gap-4 px-5 py-3 border-t border-slate-800/80 text-[11px] text-slate-400 shrink-0">
            <span className="flex items-center gap-1"><Heart className="w-3.5 h-3.5 text-rose-500" />{fmtCount(stats.digg_count)}</span>
            <span className="flex items-center gap-1"><MessageCircle className="w-3.5 h-3.5 text-sky-500" />{fmtCount(stats.comment_count)}</span>
            <span className="flex items-center gap-1"><Star className="w-3.5 h-3.5 text-amber-500" />{fmtCount(stats.collect_count)}</span>
            <span className="flex items-center gap-1"><Share2 className="w-3.5 h-3.5 text-emerald-500" />{fmtCount(stats.share_count)}</span>
            {info.create_time && (
              <span className="ml-auto text-slate-500">
                {new Date(info.create_time * 1000).toLocaleString('zh-CN', { hour12: false })}
              </span>
            )}
            {!isNote && (
              <span className="flex items-center gap-1 text-slate-500"><Play className="w-3 h-3" />已标记已读</span>
            )}
          </div>
        )}
      </motion.div>
    </motion.div>
  );
};
