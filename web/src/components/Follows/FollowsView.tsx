import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { AnimatePresence, motion } from 'motion/react';
import {
  Heart,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  Tag,
  Trash2,
  UserPlus,
  Users,
  X,
} from 'lucide-react';
import * as api from '../../api';
import { Account } from '../../types';
import { AuthorPage } from './AuthorPage';
import { FollowAvatar } from './FollowAvatar';
import { GroupEditDialog } from './GroupEditDialog';

interface FollowsViewProps {
  accounts: Account[];
  showToast: (msg: string, type?: 'success' | 'info' | 'error') => void;
}

const fmtDate = (iso?: string | null) => (iso || '').replace('T', ' ').slice(0, 16);

/** 特别关注主路由（/follows）：关注列表拉取 → 添加特别关注（分组）→ 一键更新最新视频。 */
export const FollowsView: React.FC<FollowsViewProps> = ({ accounts, showToast }) => {
  const location = useLocation();
  const navigate = useNavigate();

  // 子路由：/follows → 列表；/follows/author/:secUid → 博主主页
  const authorMatch = location.pathname.match(/^\/follows\/author\/([^/]+)/);

  const douyinAccounts = useMemo(
    () => accounts.filter((a) => a.platform === 'douyin' && a.status === 'active'),
    [accounts]
  );
  const [browseAccountId, setBrowseAccountId] = useState('');
  useEffect(() => {
    if (!browseAccountId && douyinAccounts.length) setBrowseAccountId(douyinAccounts[0].id);
  }, [douyinAccounts, browseAccountId]);

  // 博主列表
  const [authors, setAuthors] = useState<api.FollowAuthorRow[]>([]);
  const [groups, setGroups] = useState<{ group_name: string; count: number }[]>([]);
  const [activeGroup, setActiveGroup] = useState(''); // '' = 全部
  const [listLoading, setListLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);

  // 关注列表弹窗
  const [followOpen, setFollowOpen] = useState(false);
  const [followLoading, setFollowLoading] = useState(false);
  const [followings, setFollowings] = useState<api.FollowingUserRow[]>([]);
  const [followQuery, setFollowQuery] = useState('');
  const [addingUid, setAddingUid] = useState('');

  // 分组设置弹窗：添加特别关注成功后弹出指定分组；列表卡片「设置分组」共用
  const [groupEditUid, setGroupEditUid] = useState<api.FollowAuthorRow | null>(null);

  const reloadAuthors = useCallback(async () => {
    setListLoading(true);
    try {
      const res = await api.listFollowAuthors();
      setAuthors(res.authors);
      setGroups(res.groups);
    } catch (e: any) {
      showToast(e.message || '特别关注列表加载失败', 'error');
    } finally {
      setListLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    if (!authorMatch) reloadAuthors();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);

  const filteredAuthors = useMemo(
    () =>
      activeGroup === ''
        ? authors
        : activeGroup === '__none__'
          ? authors.filter((a) => !a.group_name)
          : authors.filter((a) => a.group_name === activeGroup),
    [authors, activeGroup]
  );

  const existingUids = useMemo(() => new Set(authors.map((a) => a.sec_uid)), [authors]);

  // ---------- 动作 ----------

  const openFollowList = async () => {
    if (!browseAccountId) {
      showToast('没有可用的抖音账号（需 active 状态），请先创建并登录', 'error');
      return;
    }
    setFollowOpen(true);
    setFollowLoading(true);
    setFollowings([]);
    try {
      const res = await api.fetchFollowing(browseAccountId);
      setFollowings(res.followings);
      showToast(`已拉取 ${res.total} 位关注博主`, 'info');
    } catch (e: any) {
      showToast(e.message || '关注列表拉取失败', 'error');
      setFollowOpen(false);
    } finally {
      setFollowLoading(false);
    }
  };

  const addAuthor = async (u: api.FollowingUserRow) => {
    setAddingUid(u.sec_uid);
    try {
      await api.addFollowAuthor({
        sec_uid: u.sec_uid,
        account_id: browseAccountId,
        uid: u.uid,
        nickname: u.nickname || '',
        unique_id: u.unique_id || '',
        avatar_url: u.avatar_url || '',
        signature: u.signature || '',
        follower_count: u.follower_count,
      });
      showToast(`已添加「${u.nickname || u.sec_uid.slice(0, 16)}…」为特别关注`);
      await reloadAuthors();
      // 添加成功后弹出分组设置（跳过 = 未分组）
      setGroupEditUid({
        sec_uid: u.sec_uid, platform: 'douyin', nickname: u.nickname || '',
        group_name: '', follower_count: u.follower_count ?? undefined,
      } as api.FollowAuthorRow);
    } catch (e: any) {
      showToast(e.message || '添加失败', 'error');
    } finally {
      setAddingUid('');
    }
  };

  const removeAuthor = async (a: api.FollowAuthorRow) => {
    if (!window.confirm(`确定取消特别关注「${a.nickname || a.sec_uid.slice(0, 16)}…」？（不影响已入库作品）`)) return;
    try {
      await api.deleteFollowAuthor(a.sec_uid);
      showToast(`已移除「${a.nickname || a.sec_uid.slice(0, 16)}…」`);
      reloadAuthors();
    } catch (e: any) {
      showToast(e.message || '移除失败', 'error');
    }
  };

  const syncAll = async (secUid?: string) => {
    setSyncing(true);
    try {
      const res = await api.syncFollowPosts(secUid ? { sec_uids: [secUid], account_id: browseAccountId } : {});
      const failed = res.results.filter((r) => r.status === 'failed');
      if (failed.length) {
        showToast(
          `同步完成：${res.ok}/${res.total} 位博主，新增 ${res.new} 条；失败：${failed
            .slice(0, 3)
            .map((f) => f.nickname || f.sec_uid.slice(0, 8))
            .join('、')}${failed.length > 3 ? ' 等' : ''}`,
          'error'
        );
      } else {
        showToast(`同步完成：${res.ok} 位博主，本次新增 ${res.new} 条作品`);
      }
      if (!secUid) reloadAuthors();
    } catch (e: any) {
      showToast(e.message || '同步失败', 'error');
    } finally {
      setSyncing(false);
    }
  };

  // ---------- 博主主页子路由 ----------

  if (authorMatch) {
    return (
      <AuthorPage
        secUid={decodeURIComponent(authorMatch[1])}
        accounts={accounts}
        browseAccountId={browseAccountId}
        showToast={showToast}
        onBack={() => navigate('/follows')}
        onSyncOne={async (uid) => {
          await api.syncFollowPosts({ sec_uids: [uid], account_id: browseAccountId });
          showToast('该博主最新视频已入库');
        }}
      />
    );
  }

  const query = followQuery.trim().toLowerCase();
  const filteredFollowings = query
    ? followings.filter(
        (f) =>
          (f.nickname || '').toLowerCase().includes(query) ||
          (f.unique_id || '').toLowerCase().includes(query)
      )
    : followings;

  // ---------- 列表视图 ----------

  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-5">
      {/* 工具栏 */}
      <div className="bg-white dark:bg-[#161B26] rounded-3xl border border-slate-200/80 dark:border-slate-800 p-4 shadow-2xs flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1.5 text-sm font-bold text-slate-900 dark:text-white">
          <Heart className="w-4 h-4 text-rose-500 fill-rose-500/20" />
          特别关注
          <span className="text-xs font-medium text-slate-400">{authors.length} 位博主</span>
        </div>

        <div className="flex items-center gap-2 ml-auto flex-wrap">
          <select
            value={browseAccountId}
            onChange={(e) => setBrowseAccountId(e.target.value)}
            className="px-3 py-2 rounded-xl text-xs font-medium bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 border-0 outline-none cursor-pointer"
            title="用于拉取关注列表/浏览作品的抖音账号"
          >
            {douyinAccounts.length === 0 && <option value="">无可用抖音账号</option>}
            {douyinAccounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
          <button
            onClick={openFollowList}
            disabled={followLoading}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-700 active:scale-95 transition-all disabled:opacity-50 cursor-pointer"
          >
            <UserPlus className="w-3.5 h-3.5" />
            拉取关注列表
          </button>
          <button
            onClick={() => syncAll()}
            disabled={syncing || authors.length === 0}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold bg-slate-900 dark:bg-white text-white dark:text-slate-900 hover:opacity-90 active:scale-95 transition-all disabled:opacity-50 cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${syncing ? 'animate-spin' : ''}`} />
            {syncing ? '更新中…' : '一键更新最新视频'}
          </button>
        </div>
      </div>

      {/* 分组过滤 */}
      <div className="flex items-center gap-2 flex-wrap">
        {[
          { key: '', label: `全部 (${authors.length})` },
          { key: '__none__', label: `未分组 (${authors.filter((a) => !a.group_name).length})` },
          ...groups.map((g) => ({ key: g.group_name, label: `${g.group_name} (${g.count})` })),
        ].map((g) => (
          <button
            key={g.key}
            onClick={() => setActiveGroup(g.key)}
            className={`px-3 py-1.5 rounded-full text-xs font-semibold border transition-all cursor-pointer ${
              activeGroup === g.key
                ? 'bg-indigo-600 border-indigo-600 text-white shadow-sm'
                : 'bg-white dark:bg-[#161B26] border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-300 hover:border-slate-300 dark:hover:border-slate-700'
            }`}
          >
            {g.label}
          </button>
        ))}
      </div>

      {/* 博主网格 */}
      {listLoading && authors.length === 0 ? (
        <div className="flex items-center justify-center gap-2 py-20 text-slate-400">
          <Loader2 className="w-6 h-6 animate-spin" />
          <span className="text-xs">加载中…</span>
        </div>
      ) : filteredAuthors.length === 0 ? (
        <div className="flex flex-col items-center gap-3 py-20 text-slate-400">
          <Heart className="w-10 h-10 opacity-30" />
          <p className="text-xs">
            {authors.length === 0
              ? '还没有特别关注的博主，点击右上角「拉取关注列表」从关注中挑选'
              : '该分组下暂无博主'}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {filteredAuthors.map((a, idx) => (
            <motion.div
              key={a.sec_uid}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: Math.min(idx * 25, 250) / 1000 }}
              onClick={() => navigate(`/follows/author/${encodeURIComponent(a.sec_uid)}`)}
              className="bg-white dark:bg-[#161B26] rounded-[20px] border border-slate-200/80 dark:border-slate-800 shadow-2xs hover:shadow-lg transition-all duration-200 p-4 cursor-pointer group relative overflow-hidden"
            >
              {/* 未读作品数角标 */}
              {!!a.unread && (
                <span className="absolute top-3 right-3 min-w-[20px] h-5 px-1.5 rounded-full bg-sky-500 text-white text-[10px] font-bold flex items-center justify-center shadow z-10">
                  {a.unread > 99 ? '99+' : a.unread}
                </span>
              )}
              <div className="flex items-start gap-3">
                <FollowAvatar
                  secUid={a.sec_uid}
                  nickname={a.nickname}
                  className="w-12 h-12 rounded-full ring-2 ring-slate-100 dark:ring-slate-800"
                />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white truncate group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors">
                      {a.nickname || a.sec_uid.slice(0, 20) + '…'}
                    </h3>
                  </div>
                  <p className="text-[11px] text-slate-400 mt-0.5 flex items-center gap-1">
                    <Users className="w-3 h-3" />
                    {a.follower_count != null
                      ? a.follower_count >= 10000
                        ? `${(a.follower_count / 10000).toFixed(1)}w 粉丝`
                        : `${a.follower_count} 粉丝`
                      : '—'}
                  </p>
                  {a.signature && (
                    <p className="text-[11px] text-slate-400 dark:text-slate-500 mt-1 line-clamp-2">{a.signature}</p>
                  )}
                </div>
              </div>
              <div className="flex items-center justify-between mt-3 pt-3 border-t border-slate-100 dark:border-slate-800/80">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setGroupEditUid(a);
                  }}
                  className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-semibold text-slate-500 dark:text-slate-400 hover:text-indigo-600 dark:hover:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-colors cursor-pointer"
                >
                  <Tag className="w-3 h-3" />
                  {a.group_name || '设置分组'}
                </button>
                <span className="text-[10px] text-slate-400">
                  {a.last_synced_at ? `同步于 ${fmtDate(a.last_synced_at)}` : '尚未同步'}
                </span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    removeAuthor(a);
                  }}
                  className="w-6 h-6 rounded-full flex items-center justify-center text-slate-300 hover:text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950/40 transition-colors cursor-pointer"
                  title="取消特别关注"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </motion.div>
          ))}
        </div>
      )}

      {/* 关注列表弹窗 */}
      <AnimatePresence>
        {followOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4"
            onClick={() => setFollowOpen(false)}
          >
            <motion.div
              initial={{ scale: 0.95, y: 16 }}
              animate={{ scale: 1, y: 0 }}
              exit={{ scale: 0.95, y: 16 }}
              transition={{ type: 'spring', stiffness: 320, damping: 30 }}
              onClick={(e) => e.stopPropagation()}
              className="w-full max-w-2xl max-h-[85vh] bg-white dark:bg-[#111622] rounded-3xl border border-slate-200 dark:border-slate-800 shadow-2xl flex flex-col overflow-hidden"
            >
              <div className="px-5 py-4 border-b border-slate-100 dark:border-slate-800 flex items-center gap-3 shrink-0">
                <h3 className="text-sm font-bold text-slate-900 dark:text-white">关注列表（{followings.length}）</h3>
                <span className="text-[11px] text-slate-400 ml-auto hidden sm:inline">
                  添加后可指定分组
                </span>
                <button
                  onClick={() => setFollowOpen(false)}
                  className="w-8 h-8 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-500 hover:text-slate-900 dark:hover:text-white flex items-center justify-center transition-colors cursor-pointer"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <div className="px-5 py-3 border-b border-slate-100 dark:border-slate-800 shrink-0">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
                  <input
                    value={followQuery}
                    onChange={(e) => setFollowQuery(e.target.value)}
                    placeholder="搜索昵称 / 抖音号"
                    className="w-full pl-9 pr-3 py-2 rounded-xl text-xs bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 outline-none border-0"
                  />
                </div>
              </div>

              <div className="flex-1 overflow-y-auto p-3 space-y-1.5">
                {followLoading ? (
                  <div className="flex items-center justify-center gap-2 py-16 text-slate-400">
                    <Loader2 className="w-5 h-5 animate-spin" />
                    <span className="text-xs">正在拉取关注列表…</span>
                  </div>
                ) : filteredFollowings.length === 0 ? (
                  <div className="text-center py-16 text-xs text-slate-400">
                    {followings.length === 0 ? '暂无关注' : '没有匹配的博主'}
                  </div>
                ) : (
                  filteredFollowings.map((f) => {
                    const added = existingUids.has(f.sec_uid);
                    return (
                      <div
                        key={f.sec_uid}
                        className="flex items-center gap-3 px-3 py-2.5 rounded-2xl hover:bg-slate-50 dark:hover:bg-slate-800/60 transition-colors"
                      >
                        {f.avatar_url ? (
                          <img
                            src={api.mediaUrl(f.avatar_url)}
                            alt={f.nickname || ''}
                            className="w-9 h-9 rounded-full object-cover shrink-0"
                          />
                        ) : (
                          <div className="w-9 h-9 rounded-full bg-slate-200 dark:bg-slate-700 shrink-0" />
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
                          <p className="text-[10px] text-slate-400 truncate">
                            {f.unique_id ? `@${f.unique_id} · ` : ''}
                            {f.follower_count != null
                              ? `${(f.follower_count / 10000).toFixed(1)}w 粉丝`
                              : ''}
                          </p>
                        </div>
                        <button
                          onClick={() => !added && addAuthor(f)}
                          disabled={added || addingUid === f.sec_uid}
                          className={`inline-flex items-center gap-1 px-3 py-1.5 rounded-xl text-[11px] font-semibold shrink-0 transition-all cursor-pointer ${
                            added
                              ? 'bg-emerald-50 dark:bg-emerald-950/50 text-emerald-600 dark:text-emerald-400 cursor-default'
                              : 'bg-indigo-600 text-white hover:bg-indigo-500 active:scale-95'
                          }`}
                        >
                          {addingUid === f.sec_uid ? (
                            <Loader2 className="w-3 h-3 animate-spin" />
                          ) : added ? (
                            <Heart className="w-3 h-3 fill-current" />
                          ) : (
                            <Plus className="w-3 h-3" />
                          )}
                          {added ? '已特别关注' : '特别关注'}
                        </button>
                      </div>
                    );
                  })
                )}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* 分组设置弹窗：添加成功后指定分组 / 卡片「设置分组」共用 */}
      <AnimatePresence>
        {groupEditUid && (
          <GroupEditDialog
            secUid={groupEditUid.sec_uid}
            nickname={groupEditUid.nickname}
            initialGroup={groupEditUid.group_name || ''}
            groups={groups}
            onClose={() => setGroupEditUid(null)}
            onSaved={(group) => {
              showToast(group ? `已设分组「${group}」` : '已移出分组');
              reloadAuthors();
            }}
            onError={(msg) => showToast(msg, 'error')}
          />
        )}
      </AnimatePresence>
    </div>
  );
};
