import React, { useState } from 'react';
import { Account, AccountStatus, PlatformId } from '../../types';
import { PLATFORMS } from '../../data/platforms';
import * as api from '../../api';
import { Plus, CheckCircle2, AlertTriangle, Ban, RefreshCw, QrCode, ArrowUpRight, Search, Clock, Monitor, ChevronRight } from 'lucide-react';
import { SiteIcon, usePlatformInfos } from '../SiteIcon';

interface AccountsListProps {
  accounts: Account[];
  onSelectAccount: (account: Account) => void;
  onOpenCreateModal: () => void;
  onOpenLoginModal: (account: Account) => void;
  onQuickCheckHealth: (account: Account) => void;
  /** 批量刷新账号身份信息（昵称/头像/收藏夹）；结果提示由 App 层负责。 */
  onRefreshProfiles: () => Promise<api.RefreshProfilesResult>;
  onRefreshProfile: (account: Account) => Promise<void>;
  /** 批量刷新实时进度；null = 未在批量刷新（当前账号卡片高亮）。 */
  profileRefresh: api.ProfileRefreshProgress | null;
}

export const AccountsList: React.FC<AccountsListProps> = ({
  accounts,
  onSelectAccount,
  onOpenCreateModal,
  onOpenLoginModal,
  onQuickCheckHealth,
  onRefreshProfiles,
  onRefreshProfile,
  profileRefresh,
}) => {
  const [platformFilter, setPlatformFilter] = useState<string>('all');
  // mock 未收录的平台（如 threads）由此兜底 display_name / icon_url
  const platformInfos = usePlatformInfos();
  const [searchQuery, setSearchQuery] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  const filteredAccounts = accounts.filter((acc) => {
    const matchesPlatform = platformFilter === 'all' || acc.platform === platformFilter;
    const matchesSearch =
      acc.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (acc.ownerNickname && acc.ownerNickname.toLowerCase().includes(searchQuery.toLowerCase())) ||
      acc.platform.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesPlatform && matchesSearch;
  });

  const getStatusBadge = (status: AccountStatus) => {
    switch (status) {
      case 'active':
        return (
          <span className="inline-flex items-center gap-1 text-[11px] font-bold text-emerald-700 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950 px-2.5 py-1 rounded-full border border-emerald-200/60 dark:border-emerald-800">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            已启用
          </span>
        );
      case 'expired':
        return (
          <span className="inline-flex items-center gap-1 text-[11px] font-bold text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-950 px-2.5 py-1 rounded-full border border-amber-200/60 dark:border-amber-800">
            <AlertTriangle className="w-3 h-3 text-amber-600" />
            登录过期
          </span>
        );
      case 'disabled':
        return (
          <span className="inline-flex items-center gap-1 text-[11px] font-bold text-slate-500 dark:text-slate-400 bg-slate-100 dark:bg-slate-800 px-2.5 py-1 rounded-full border border-slate-200 dark:border-slate-700">
            <Ban className="w-3 h-3 text-slate-400" />
            已禁用
          </span>
        );
      case 'logging_in':
        return (
          <span className="inline-flex items-center gap-1 text-[11px] font-bold text-indigo-700 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-950 px-2.5 py-1 rounded-full border border-indigo-200/60 dark:border-indigo-800">
            <RefreshCw className="w-3 h-3 text-indigo-600 animate-spin" />
            登录中
          </span>
        );
    }
  };

  return (
    <div id="accounts-management-view" className="space-y-6">
      {/* Top Banner / Actions bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
            账号管理
          </h2>
          <p className="text-xs sm:text-sm text-slate-500 dark:text-slate-400 mt-0.5">
            管理你在各平台的登录身份，是使用 FavAPI 进行全量与增量收藏抓取的起点。
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={refreshing || accounts.length === 0}
            onClick={async () => {
              setRefreshing(true);
              try {
                await onRefreshProfiles();
              } catch {
                /* 失败提示由 App 层 toast */
              } finally {
                setRefreshing(false);
              }
            }}
            className="inline-flex items-center justify-center gap-2 px-4 py-2.5 bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 rounded-2xl text-xs sm:text-sm font-bold shadow-sm border border-slate-200 dark:border-slate-700 transition-transform active:scale-98 disabled:opacity-50 disabled:cursor-not-allowed"
            title="重新拉取所有账号的昵称/头像/收藏夹信息（除微信收藏外均支持）"
          >
            <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
            {refreshing
              ? `刷新中 (${(profileRefresh?.done ?? 0) + 1}/${accounts.length})`
              : '刷新账号信息'}
          </button>

          <button
            type="button"
            onClick={onOpenCreateModal}
            className="inline-flex items-center justify-center gap-2 px-4 py-2.5 bg-slate-900 hover:bg-slate-800 dark:bg-slate-700 dark:hover:bg-slate-600 text-white rounded-2xl text-xs sm:text-sm font-bold shadow-sm transition-transform active:scale-98"
          >
            <Plus className="w-4 h-4" />
            创建新账号
          </button>
        </div>
      </div>

      {/* Filter and Search */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-white dark:bg-[#161B26] p-3 rounded-2xl border border-slate-200/80 dark:border-slate-800 shadow-2xs">
        {/* Platform filter tabs */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0">
          <button
            type="button"
            onClick={() => setPlatformFilter('all')}
            className={`px-3 py-1.5 rounded-xl text-xs font-semibold whitespace-nowrap transition-colors ${
              platformFilter === 'all'
                ? 'bg-slate-900 dark:bg-slate-700 text-white shadow-2xs'
                : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700'
            }`}
          >
            全部平台 ({accounts.length})
          </button>
          {PLATFORMS.filter((p) => p.isSupported).map((p) => {
            const count = accounts.filter((a) => a.platform === p.id).length;
            return (
              <button
                key={p.id}
                type="button"
                onClick={() => setPlatformFilter(p.id)}
                className={`px-3 py-1.5 rounded-xl text-xs font-semibold whitespace-nowrap transition-colors flex items-center gap-1.5 ${
                  platformFilter === p.id
                    ? 'bg-slate-900 dark:bg-slate-700 text-white shadow-2xs'
                    : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700'
                }`}
              >
                <span>{p.name.split(' ')[0]}</span>
                <span className="text-[10px] opacity-70">({count})</span>
              </button>
            );
          })}
        </div>

        {/* Search input */}
        <div className="relative">
          <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="搜索账号名、昵称..."
            className="pl-8 pr-3 py-1.5 rounded-xl border border-slate-200 dark:border-slate-700 text-xs w-full sm:w-56 focus:outline-none focus:ring-2 focus:ring-slate-900 bg-slate-50/50 dark:bg-slate-800 dark:text-slate-200"
          />
        </div>
      </div>

      {/* Account Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 sm:gap-5">
        {filteredAccounts.map((account, idx) => {
          const platform = PLATFORMS.find((p) => p.id === account.platform);
          const platformName = platform?.name || platformInfos[account.platform]?.display_name || account.platform;
          const isRefreshing = profileRefresh?.accountId === account.id;
          return (
            <div
              key={account.id}
              id={`account-card-${account.id}`}
              className={`anim-card-enter bg-white dark:bg-[#161B26] rounded-[26px] p-5 sm:p-6 border shadow-2xs hover:shadow-md dark:hover:shadow-slate-950/40 transition-all flex flex-col justify-between group ${
                isRefreshing
                  ? 'border-indigo-400 dark:border-indigo-500 ring-2 ring-indigo-400/40 shadow-md'
                  : 'border-slate-200/80 dark:border-slate-800'
              }`}
              style={{ animationDelay: `${Math.min(idx * 30, 240)}ms` }}
            >
              {/* Top row: Platform & Status */}
              <div>
                <div className="flex items-center justify-between gap-2 mb-3">
                  <div className="flex items-center gap-2">
                    <span
                      className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold border ${
                        platform?.badgeBg || 'bg-slate-100 text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700'
                      }`}
                    >
                      <SiteIcon platform={account.platform} name={platformName} className="w-3.5 h-3.5" />
                      {platformName}
                    </span>
                    {isRefreshing && (
                      <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-indigo-700 dark:text-indigo-300 bg-indigo-50 dark:bg-indigo-950 px-2 py-0.5 rounded-full border border-indigo-200 dark:border-indigo-800">
                        <RefreshCw className="w-3 h-3 animate-spin" />
                        刷新中 ({(profileRefresh?.done ?? 0) + 1}/{profileRefresh?.total})
                      </span>
                    )}
                    {account.isBrowserOpen && (
                      <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-sky-700 dark:text-sky-400 bg-sky-50 dark:bg-sky-950 px-2 py-0.5 rounded-full border border-sky-200 dark:border-sky-800">
                        <Monitor className="w-3 h-3" />
                        浏览器已打开
                      </span>
                    )}
                  </div>
                  {getStatusBadge(account.status)}
                </div>

                {/* Account Name (clickable into details) */}
                <div className="flex items-start justify-between gap-3">
                  <div
                    onClick={() => onSelectAccount(account)}
                    className="cursor-pointer group-hover:text-indigo-600 transition-colors"
                  >
                    <h3 className="text-base sm:text-lg font-bold text-slate-900 dark:text-white tracking-tight flex items-center gap-1.5">
                      {account.name}
                      <ArrowUpRight className="w-4 h-4 opacity-0 group-hover:opacity-100 transition-opacity" />
                    </h3>
                    <p className="text-xs text-slate-500 dark:text-slate-400 font-mono mt-0.5">
                      ID: {account.id}
                    </p>
                  </div>

                  {/* Owner Avatar if available */}
                  {account.ownerAvatar && (
                    <img
                      src={account.ownerAvatar}
                      alt={account.ownerNickname || ''}
                      title={`当前身份: ${account.ownerNickname}`}
                      className="w-10 h-10 rounded-full border-2 border-slate-100 dark:border-slate-800 object-cover shadow-2xs shrink-0"
                      referrerPolicy="no-referrer"
                    />
                  )}
                </div>

                {/* Nickname & Folder counts preview (Bilibili/XHS specific) */}
                {account.ownerNickname && (
                  <div className="mt-3 py-2 px-3 bg-slate-50 dark:bg-slate-800 rounded-xl text-xs text-slate-700 dark:text-slate-300 flex items-center justify-between border border-slate-100 dark:border-slate-700">
                    <span className="font-medium text-slate-600 dark:text-slate-400">
                      主号昵称: <strong className="text-slate-900 dark:text-white">{account.ownerNickname}</strong>
                    </span>
                    {account.folders && (
                      <span className="text-[11px] text-slate-500 dark:text-slate-400">
                        {account.folders.length} 个收藏夹
                      </span>
                    )}
                  </div>
                )}

                {/* Timestamps */}
                <div className="mt-4 grid grid-cols-2 gap-2 text-[11px] text-slate-500 dark:text-slate-400">
                  <div className="flex items-center gap-1.5">
                    <Clock className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                    <span className="truncate">最后登录: {account.lastLoginTime.split(' ')[0]}</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-slate-300" />
                    <span className="truncate">最后使用: {account.lastUsedTime}</span>
                  </div>
                </div>
              </div>

              {/* Bottom Action Buttons */}
              <div className="pt-4 mt-4 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5">
                  {account.platform !== 'wechat' && <button
                    type="button"
                    onClick={() => onOpenLoginModal(account)}
                    className="px-3 py-1.5 rounded-xl text-xs font-semibold text-slate-700 dark:text-slate-200 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 hover:text-slate-900 dark:hover:text-white transition-colors inline-flex items-center gap-1"
                    title="在真实浏览器窗口中扫码续期"
                  >
                    <QrCode className="w-3.5 h-3.5" />
                    {account.status === 'expired' ? '重新扫码' : '扫码登录'}
                  </button>}

                  {account.platform !== 'wechat' && <button
                    type="button"
                    onClick={() => onQuickCheckHealth(account)}
                    className="px-2.5 py-1.5 rounded-xl text-xs font-semibold text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                    title="验证当前登录凭据是否有效"
                  >
                    检查
                  </button>}
                  {account.platform !== 'wechat' && <button
                    type="button"
                    onClick={() => onRefreshProfile(account)}
                    className="p-1.5 rounded-xl text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                    title="刷新此账号信息"
                  >
                    <RefreshCw className="w-3.5 h-3.5" />
                  </button>}
                </div>

                <button
                  type="button"
                  onClick={() => onSelectAccount(account)}
                  className="inline-flex items-center gap-1 text-xs font-bold text-slate-800 dark:text-slate-200 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors"
                >
                  进入工作台
                  <ChevronRight className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
