import React, { useMemo, useState } from 'react';
import { Account } from '../../../types';
import * as api from '../../../api';
import { Heart, Loader2, Plus, Search, UserPlus, Users } from 'lucide-react';

interface FollowingListProps {
  account: Account;
}

/**
 * 账号详情「关注列表」Tab（douyin）：点击拉取当前账号的关注博主，
 * 行内可直接添加为特别关注（添加后按钮变实心红心，分组管理去「特别关注」页）。
 * 拉取需读取浏览器 profile（起一次无头 Chromium 读 cookie），按需手动触发不自动加载。
 */
export const FollowingList: React.FC<FollowingListProps> = ({ account }) => {
  const [loading, setLoading] = useState(false);
  const [followings, setFollowings] = useState<api.FollowingUserRow[] | null>(null);
  const [total, setTotal] = useState(0);
  const [specialUids, setSpecialUids] = useState<Set<string>>(new Set());
  const [addingUid, setAddingUid] = useState('');
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      // 已特别关注的 sec_uid 一并拉取，行内标记避免重复添加
      const [res, authors] = await Promise.all([
        api.fetchFollowing(account.id),
        api.listFollowAuthors().catch(() => ({ authors: [] as api.FollowAuthorRow[] })),
      ]);
      setFollowings(res.followings);
      setTotal(res.total);
      setSpecialUids(new Set(authors.authors.map((a) => a.sec_uid)));
    } catch (e: any) {
      setError(e.message || '关注列表拉取失败');
    } finally {
      setLoading(false);
    }
  };

  const addSpecial = async (u: api.FollowingUserRow) => {
    setAddingUid(u.sec_uid);
    try {
      await api.addFollowAuthor({
        sec_uid: u.sec_uid,
        account_id: account.id,
        uid: u.uid,
        nickname: u.nickname || '',
        unique_id: u.unique_id || '',
        avatar_url: u.avatar_url || '',
        signature: u.signature || '',
        follower_count: u.follower_count,
      });
      setSpecialUids((prev) => new Set(prev).add(u.sec_uid));
    } catch (e: any) {
      setError(e.message || '添加特别关注失败');
    } finally {
      setAddingUid('');
    }
  };

  const q = query.trim().toLowerCase();
  const visible = useMemo(
    () =>
      q
        ? (followings || []).filter(
            (f) =>
              (f.nickname || '').toLowerCase().includes(q) ||
              (f.unique_id || '').toLowerCase().includes(q)
          )
        : followings || [],
    [followings, q]
  );

  return (
    <div className="space-y-4">
      {/* 工具行：说明 + 搜索 + 拉取按钮 */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="text-xs text-slate-500 dark:text-slate-400">
          {followings ? (
            <>
              共 <span className="font-bold text-slate-800 dark:text-slate-200">{total}</span> 位关注博主
              {q && <span className="ml-1">，匹配 {visible.length} 位</span>}
            </>
          ) : (
            '拉取当前账号的关注博主，可一键添加为特别关注'
          )}
        </div>
        <div className="flex items-center gap-2 ml-auto">
          {followings && followings.length > 0 && (
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="搜索昵称 / 抖音号"
                className="w-48 pl-8 pr-3 py-1.5 rounded-xl text-xs bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 outline-none border-0"
              />
            </div>
          )}
          <button
            type="button"
            onClick={load}
            disabled={loading}
            className="px-3.5 py-2 rounded-xl text-xs font-semibold bg-slate-900 dark:bg-white text-white dark:text-slate-900 hover:opacity-90 active:scale-95 transition-all disabled:opacity-60 inline-flex items-center gap-1.5 cursor-pointer"
          >
            {loading ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Plus className="w-3.5 h-3.5" />
            )}
            {loading ? '拉取中…' : followings ? '刷新关注列表' : '拉取关注列表'}
          </button>
        </div>
      </div>

      {error && (
        <p className="text-xs text-rose-600 dark:text-rose-400 bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 rounded-xl px-3 py-2">
          {error}
        </p>
      )}

      {/* 列表主体 */}
      {loading && !followings ? (
        <div className="flex items-center justify-center gap-2 py-16 text-slate-400">
          <Loader2 className="w-5 h-5 animate-spin" />
          <span className="text-xs">正在读取登录态并拉取关注列表（约数秒）…</span>
        </div>
      ) : !followings ? (
        <div className="flex flex-col items-center gap-2 py-16 text-slate-400">
          <UserPlus className="w-8 h-8 opacity-40" />
          <p className="text-xs">点击「拉取关注列表」获取博主列表（需读取浏览器登录态）</p>
        </div>
      ) : visible.length === 0 ? (
        <div className="text-center py-16 text-xs text-slate-400">
          {followings.length === 0 ? '该账号暂无关注' : '没有匹配的博主'}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
          {visible.map((f) => {
            const added = specialUids.has(f.sec_uid);
            return (
              <div
                key={f.sec_uid}
                className="flex items-center gap-3 p-3 rounded-2xl border border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/60 transition-colors"
              >
                {f.avatar_url ? (
                  <img
                    src={api.mediaUrl(f.avatar_url)}
                    alt={f.nickname || ''}
                    className="w-10 h-10 rounded-full object-cover shrink-0"
                  />
                ) : (
                  <div className="w-10 h-10 rounded-full bg-slate-200 dark:bg-slate-700 flex items-center justify-center shrink-0">
                    <Users className="w-4 h-4 text-slate-400" />
                  </div>
                )}
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-semibold text-slate-900 dark:text-white truncate">
                    {f.nickname || '未知博主'}
                    {f.is_top && (
                      <span className="ml-1.5 px-1 py-px rounded text-[9px] font-bold bg-amber-100 dark:bg-amber-950/60 text-amber-600 dark:text-amber-400 align-middle">
                        置顶
                      </span>
                    )}
                  </p>
                  <p className="text-[11px] text-slate-400 truncate">
                    {f.unique_id ? `@${f.unique_id} · ` : ''}
                    {f.follower_count != null
                      ? f.follower_count >= 10000
                        ? `${(f.follower_count / 10000).toFixed(1)}w 粉丝`
                        : `${f.follower_count} 粉丝`
                      : ''}
                    {f.aweme_count != null ? ` · ${f.aweme_count} 作品` : ''}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => !added && addSpecial(f)}
                  disabled={added || addingUid === f.sec_uid}
                  className={`inline-flex items-center gap-1 px-3 py-1.5 rounded-xl text-[11px] font-semibold shrink-0 transition-all cursor-pointer ${
                    added
                      ? 'bg-emerald-50 dark:bg-emerald-950/50 text-emerald-600 dark:text-emerald-400 cursor-default'
                      : 'bg-indigo-600 text-white hover:bg-indigo-500 active:scale-95'
                  }`}
                >
                  {addingUid === f.sec_uid ? (
                    <Loader2 className="w-3 h-3 animate-spin" />
                  ) : (
                    <Heart className={`w-3 h-3 ${added ? 'fill-current' : ''}`} />
                  )}
                  {added ? '已特别关注' : '特别关注'}
                </button>
              </div>
            );
          })}
        </div>
      )}

      {followings && followings.length > 0 && (
        <p className="text-[11px] text-slate-400 pt-1 border-t border-slate-100 dark:border-slate-800">
          添加后可在侧边栏「特别关注」页管理分组并追踪最新作品（播放可标记已读）
        </p>
      )}
    </div>
  );
};
