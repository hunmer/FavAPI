import React, { useCallback, useEffect, useRef, useState } from 'react';
import { motion } from 'motion/react';
import {
  ArrowLeft,
  ImageOff,
  Loader2,
  RefreshCw,
  Tag,
  Users,
} from 'lucide-react';
import * as api from '../../api';
import { Account } from '../../types';
import { PlayerModal } from './PlayerModal';
import { FollowAvatar } from './FollowAvatar';

interface AuthorPageProps {
  secUid: string;
  accounts: Account[];
  /** 当前会话默认用于浏览的抖音账号 ID */
  browseAccountId: string;
  showToast: (msg: string, type?: 'success' | 'info' | 'error') => void;
  onBack: () => void;
  /** 同步该博主最新作品入库（复用列表页逻辑） */
  onSyncOne: (secUid: string) => Promise<void>;
}

const PAGE_SIZE = 18;

/** 格式化抖音时长（毫秒） */
const fmtMs = (ms?: number | null) => {
  if (!ms || ms <= 0) return '';
  const s = Math.round(ms / 1000);
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, '0')}`;
};

const fmtDate = (iso?: string | null) => (iso || '').replace('T', ' ').slice(0, 16);

/** 博主主页路由（/follows/author/:secUid）：实时作品列表 + 播放器 + 已读标记。 */
export const AuthorPage: React.FC<AuthorPageProps> = ({
  secUid,
  accounts,
  browseAccountId,
  showToast,
  onBack,
  onSyncOne,
}) => {
  const [author, setAuthor] = useState<Partial<api.FollowAuthorRow> | null>(null);
  const [items, setItems] = useState<api.FollowPostRow[]>([]);
  const [cursor, setCursor] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [playing, setPlaying] = useState<{ awemeId: string; title?: string } | null>(null);
  const [onlyUnread, setOnlyUnread] = useState(false);
  const accountIdRef = useRef(browseAccountId);
  const isFirstLoad = useRef(true);

  const loadPage = useCallback(
    async (cur: number, append: boolean) => {
      setLoading(true);
      try {
        const res = await api.fetchAuthorPosts(secUid, cur, PAGE_SIZE, accountIdRef.current);
        setAuthor(res.author);
        setHasMore(res.has_more);
        setCursor(res.cursor || 0);
        setItems((prev) => {
          if (!append) return res.items;
          const seen = new Set(prev.map((p) => p.content_id));
          return [...prev, ...res.items.filter((r) => !seen.has(r.content_id))];
        });
      } catch (e: any) {
        showToast(e.message || '作品列表加载失败', 'error');
      } finally {
        setLoading(false);
      }
    },
    [secUid, showToast]
  );

  useEffect(() => {
    // 刷新博主信息 + 首屏作品；返回顶部
    accountIdRef.current = browseAccountId;
    isFirstLoad.current = true;
    loadPage(0, false);
    window.scrollTo({ top: 0 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [secUid, browseAccountId]);

  const handleRead = useCallback((contentId: string) => {
    setItems((prev) =>
      prev.map((p) => (p.content_id === contentId ? { ...p, read: true } : p))
    );
  }, []);

  const handleSyncOne = async () => {
    setSyncing(true);
    try {
      await onSyncOne(secUid);
      await loadPage(0, false); // 同步后刷新首屏（已读状态本地保留）
    } finally {
      setSyncing(false);
    }
  };

  const browseAccount = accounts.find((a) => a.id === accountIdRef.current);

  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-5">
      {/* 博主信息头 */}
      <div className="bg-white dark:bg-[#161B26] rounded-3xl border border-slate-200/80 dark:border-slate-800 p-5 shadow-2xs">
        <div className="flex items-start gap-4">
          <button
            onClick={onBack}
            className="w-9 h-9 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 flex items-center justify-center shrink-0 transition-colors cursor-pointer"
            aria-label="返回特别关注列表"
          >
            <ArrowLeft className="w-4.5 h-4.5" />
          </button>
          <FollowAvatar
            secUid={secUid}
            nickname={author?.nickname}
            className="w-16 h-16 rounded-full ring-2 ring-slate-200 dark:ring-slate-700"
          />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-lg font-bold text-slate-900 dark:text-white">
                {author?.nickname || '加载中…'}
              </h2>
              {author?.group_name && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 border border-indigo-200/60 dark:border-indigo-900">
                  <Tag className="w-3 h-3" />
                  {author.group_name}
                </span>
              )}
            </div>
            {author?.signature && (
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 line-clamp-2">{author.signature}</p>
            )}
            <div className="flex items-center gap-4 mt-2 text-[11px] text-slate-500 dark:text-slate-400">
              {author?.follower_count != null && (
                <span className="flex items-center gap-1">
                  <Users className="w-3.5 h-3.5" />
                  {author.follower_count >= 10000
                    ? `${(author.follower_count / 10000).toFixed(1)}w 粉丝`
                    : `${author.follower_count} 粉丝`}
                </span>
              )}
              {author?.last_synced_at && (
                <span>上次同步 {fmtDate(author.last_synced_at)}</span>
              )}
              {browseAccount && <span>经账号「{browseAccount.name}」浏览</span>}
            </div>
          </div>
          <button
            onClick={handleSyncOne}
            disabled={syncing}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold bg-slate-900 dark:bg-white text-white dark:text-slate-900 hover:opacity-90 active:scale-95 transition-all disabled:opacity-50 shrink-0 cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${syncing ? 'animate-spin' : ''}`} />
            同步最新视频
          </button>
        </div>
      </div>

      {/* 工具行：仅看未读开关 */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => setOnlyUnread((v) => !v)}
          className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold border transition-all cursor-pointer ${
            onlyUnread
              ? 'bg-sky-500 border-sky-500 text-white shadow-sm'
              : 'bg-white dark:bg-[#161B26] border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-300 hover:border-slate-300 dark:hover:border-slate-700'
          }`}
        >
          <span className={`w-1.5 h-1.5 rounded-full ${onlyUnread ? 'bg-white' : 'bg-sky-500'}`} />
          仅看未读（{items.filter((i) => !i.read).length}）
        </button>
        {onlyUnread && items.every((i) => i.read) && (
          <span className="text-[11px] text-slate-400">当前已加载作品均已读，可加载更多</span>
        )}
      </div>

      {/* 作品网格 */}
      {loading && items.length === 0 ? (
        <div className="flex items-center justify-center gap-2 py-20 text-slate-400">
          <Loader2 className="w-6 h-6 animate-spin" />
          <span className="text-xs">正在加载博主作品…</span>
        </div>
      ) : items.length === 0 ? (
        <div className="text-center py-20 text-xs text-slate-400">该博主暂无可见作品</div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
          {(onlyUnread ? items.filter((i) => !i.read) : items).map((it, idx) => (
            <motion.div
              key={it.content_id}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: Math.min(idx * 20, 200) / 1000 }}
              onClick={() => setPlaying({ awemeId: it.content_id, title: it.title || undefined })}
              className="anim-card-enter bg-white dark:bg-[#161B26] rounded-[20px] border border-slate-200/80 dark:border-slate-800 shadow-2xs hover:shadow-lg transition-all duration-200 overflow-hidden cursor-pointer group"
            >
              <div className="relative aspect-video bg-slate-100 dark:bg-slate-800 overflow-hidden">
                {it.cover_url ? (
                  <img
                    src={api.mediaUrl(it.cover_url)}
                    alt={it.title || ''}
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                    loading="lazy"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-slate-300 dark:text-slate-600">
                    <ImageOff className="w-7 h-7" />
                  </div>
                )}
                <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent pointer-events-none" />
                {/* 未读标记：已读半透明降权 */}
                {!it.read && (
                  <span className="absolute top-2 left-2 w-2.5 h-2.5 rounded-full bg-sky-500 ring-2 ring-white/70 shadow" title="未读" />
                )}
                {fmtMs(it.duration) && (
                  <span className="absolute bottom-2 right-2 px-1.5 py-0.5 rounded bg-black/65 text-white font-mono text-[10px]">
                    {fmtMs(it.duration)}
                  </span>
                )}
              </div>
              <div className="p-3">
                <p className={`text-xs font-medium line-clamp-2 leading-snug ${
                  it.read
                    ? 'text-slate-400 dark:text-slate-500'
                    : 'text-slate-900 dark:text-white'
                }`}>
                  {it.title || it.content_id}
                </p>
                <p className="text-[10px] text-slate-400 mt-1.5">{fmtDate(it.published_at)}</p>
              </div>
            </motion.div>
          ))}
        </div>
      )}

      {/* 加载更多 */}
      {hasMore && items.length > 0 && (
        <div className="flex justify-center pt-2 pb-6">
          <button
            onClick={() => loadPage(cursor, true)}
            disabled={loading}
            className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-xl text-xs font-semibold bg-white dark:bg-[#161B26] border border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-200 hover:border-slate-300 dark:hover:border-slate-700 active:scale-95 transition-all disabled:opacity-50 cursor-pointer"
          >
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
            {loading ? '加载中…' : '加载更多作品'}
          </button>
        </div>
      )}

      {/* 播放器弹窗 */}
      {playing && browseAccountId && (
        <PlayerModal
          awemeId={playing.awemeId}
          accountId={browseAccountId}
          fallbackTitle={playing.title}
          onClose={() => setPlaying(null)}
          onRead={handleRead}
        />
      )}
    </div>
  );
};
