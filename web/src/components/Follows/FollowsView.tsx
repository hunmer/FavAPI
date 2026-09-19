import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { AnimatePresence, motion } from 'motion/react';
import {
  Heart,
  Loader2,
  MoreVertical,
  Pencil,
  RefreshCw,
  Tag,
  Trash2,
  Users,
} from 'lucide-react';
import * as api from '../../api';
import { Account } from '../../types';
import { PLATFORMS } from '../../data/platforms';
import { useDismiss } from '../../hooks/useDismiss';
import { AuthorPage } from './AuthorPage';
import { FollowAvatar } from './FollowAvatar';
import { GroupEditDialog } from './GroupEditDialog';
import { confirmDialog } from '../AlertDialog';

interface FollowsViewProps {
  accounts: Account[];
  showToast: (msg: string, type?: 'success' | 'info' | 'error') => void;
  /** 一键更新完成信号（Header 按钮触发，变化时刷新博主未读数） */
  syncTick?: number;
}

const fmtDate = (iso?: string | null) => (iso || '').replace('T', ' ').slice(0, 16);

/** 特别关注主路由（/follows，多平台）：博主分组管理 + 一键更新最新视频（入口在全局 Header 右侧）。 */
export const FollowsView: React.FC<FollowsViewProps> = ({ accounts, showToast, syncTick = 0 }) => {
  const location = useLocation();
  const navigate = useNavigate();

  // 子路由：/follows → 列表；/follows/author/:secUid → 博主主页
  const authorMatch = location.pathname.match(/^\/follows\/author\/([^/]+)/);

  // 博主列表（博主主页也依赖它查 platform，全程保持加载）
  const [authors, setAuthors] = useState<api.FollowAuthorRow[]>([]);
  const [groups, setGroups] = useState<{ group_name: string; count: number }[]>([]);
  const [activeGroup, setActiveGroup] = useState(''); // '' = 全部
  const [listLoading, setListLoading] = useState(false);

  // 分组设置弹窗：列表卡片「设置分组」入口
  const [groupEditUid, setGroupEditUid] = useState<api.FollowAuthorRow | null>(null);

  // 卡片操作菜单（右上 dots 与右键共用）：x/y 为 viewport 坐标
  const [menu, setMenu] = useState<{ author: api.FollowAuthorRow; x: number; y: number } | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  useDismiss(() => setMenu(null), menu !== null, menuRef);

  // 单博主同步中标记（卡片右下角刷新按钮）
  const [syncingUid, setSyncingUid] = useState<string | null>(null);

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
    reloadAuthors();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);

  // Header 一键更新完成 → 刷新博主未读数（syncTick 首次渲染为 0 不触发）
  useEffect(() => {
    if (syncTick > 0 && !authorMatch) reloadAuthors();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [syncTick]);

  const filteredAuthors = useMemo(
    () =>
      activeGroup === ''
        ? authors
        : activeGroup === '__none__'
          ? authors.filter((a) => !a.group_name)
          : authors.filter((a) => a.group_name === activeGroup),
    [authors, activeGroup]
  );

  // ---------- 动作 ----------

  const removeAuthor = async (a: api.FollowAuthorRow) => {
    if (
      !(await confirmDialog({
        title: '取消特别关注',
        message: `确定取消特别关注「${a.nickname || a.sec_uid.slice(0, 16)}…」？（不影响已入库作品）`,
        confirmText: '移除',
        danger: true,
      }))
    ) return;
    try {
      await api.deleteFollowAuthor(a.sec_uid);
      showToast(`已移除「${a.nickname || a.sec_uid.slice(0, 16)}…」`);
      reloadAuthors();
    } catch (e: any) {
      showToast(e.message || '移除失败', 'error');
    }
  };

  /** 单博主拉取最新作品（卡片右下角刷新按钮） */
  const syncAuthor = async (a: api.FollowAuthorRow) => {
    if (syncingUid) return;
    const name = a.nickname || a.sec_uid.slice(0, 8);
    setSyncingUid(a.sec_uid);
    try {
      const res = await api.syncFollowPosts({ sec_uids: [a.sec_uid] });
      const r = res.results[0];
      if (r?.status === 'failed') {
        showToast(`「${name}」同步失败：${r.detail || '未知原因'}`, 'error');
      } else {
        showToast(`已同步「${name}」，新增 ${r?.new ?? 0} 条作品`);
      }
      reloadAuthors();
    } catch (e: any) {
      showToast(e.message || '同步失败', 'error');
    } finally {
      setSyncingUid(null);
    }
  };

  // ---------- 博主主页子路由 ----------

  if (authorMatch) {
    const secUid = decodeURIComponent(authorMatch[1]);
    return (
      <AuthorPage
        secUid={secUid}
        platform={authors.find((a) => a.sec_uid === secUid)?.platform || 'douyin'}
        accounts={accounts}
        showToast={showToast}
        onBack={() => navigate('/follows')}
      />
    );
  }

  // ---------- 列表视图 ----------

  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-5">
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
              ? '还没有特别关注的博主，去账号详情的「关注列表」从关注中挑选'
              : '该分组下暂无博主'}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {filteredAuthors.map((a, idx) => {
            const platformMeta = PLATFORMS.find((p) => p.id === a.platform);
            return (
            <motion.div
              key={a.sec_uid}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: Math.min(idx * 25, 250) / 1000 }}
              onClick={() => navigate(`/follows/author/${encodeURIComponent(a.sec_uid)}`)}
              onContextMenu={(e) => {
                e.preventDefault();
                setMenu({ author: a, x: e.clientX, y: e.clientY });
              }}
              className="bg-white dark:bg-[#161B26] rounded-[20px] border border-slate-200/80 dark:border-slate-800 shadow-2xs hover:shadow-lg transition-all duration-200 p-4 cursor-pointer group relative overflow-hidden"
            >
              {/* 右上角：hover 显示的操作菜单入口 */}
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setMenu({ author: a, x: e.clientX, y: e.clientY });
                }}
                className="absolute top-2.5 right-2.5 w-7 h-7 rounded-full flex items-center justify-center text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-all cursor-pointer z-10"
                title="更多操作"
              >
                <MoreVertical className="w-4 h-4" />
              </button>
              <div className="flex items-start gap-3">
                <div className="relative shrink-0">
                  <FollowAvatar
                    secUid={a.sec_uid}
                    nickname={a.nickname}
                    className="w-12 h-12 rounded-full ring-2 ring-slate-100 dark:ring-slate-800"
                  />
                  {/* 未读作品数角标：挂在头像右上角 */}
                  {!!a.unread && (
                    <span className="absolute -top-1.5 -right-1.5 min-w-[18px] h-[18px] px-1 rounded-full bg-sky-500 text-white text-[10px] font-bold flex items-center justify-center shadow z-10 ring-2 ring-white dark:ring-[#161B26]">
                      {a.unread > 99 ? '99+' : a.unread}
                    </span>
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white truncate group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors">
                      {a.nickname || a.sec_uid.slice(0, 20) + '…'}
                    </h3>
                    {platformMeta && (
                      <span className={`shrink-0 px-1.5 py-px rounded text-[9px] font-semibold border ${platformMeta.badgeBg}`}>
                        {platformMeta.name.split(' ')[0]}
                      </span>
                    )}
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
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-slate-400">
                    {a.last_synced_at ? `同步于 ${fmtDate(a.last_synced_at)}` : '尚未同步'}
                  </span>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      syncAuthor(a);
                    }}
                    disabled={syncingUid === a.sec_uid}
                    className="w-6 h-6 rounded-full flex items-center justify-center text-slate-300 hover:text-sky-500 hover:bg-sky-50 dark:hover:bg-sky-950/40 transition-colors cursor-pointer disabled:cursor-default disabled:text-sky-500"
                    title="同步该博主最新作品"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${syncingUid === a.sec_uid ? 'animate-spin' : ''}`} />
                  </button>
                </div>
              </div>
            </motion.div>
            );
          })}
        </div>
      )}

      {/* 卡片操作菜单：右上角 dots 与卡片右键共用，fixed 定位到事件坐标 */}
      {menu && (
        <div
          ref={menuRef}
          style={{
            left: Math.min(menu.x, window.innerWidth - 140),
            top: Math.min(menu.y, window.innerHeight - 110),
          }}
          className="fixed z-50 w-32 py-1 bg-white dark:bg-[#161B26] rounded-xl shadow-xl border border-slate-200 dark:border-slate-800 anim-modal-enter"
        >
          <button
            onClick={() => {
              setGroupEditUid(menu.author);
              setMenu(null);
            }}
            className="w-full flex items-center gap-2 px-3 py-2 text-xs font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer"
          >
            <Pencil className="w-3.5 h-3.5" />
            编辑
          </button>
          <button
            onClick={() => {
              setMenu(null);
              removeAuthor(menu.author);
            }}
            className="w-full flex items-center gap-2 px-3 py-2 text-xs font-medium text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950/40 transition-colors cursor-pointer"
          >
            <Trash2 className="w-3.5 h-3.5" />
            删除
          </button>
        </div>
      )}

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

