import React from 'react';
import { Account } from '../../../types';
import { AlertTriangle, Ban, CheckCircle2 } from 'lucide-react';

interface AccountInfoCardsProps {
  account: Account;
  localStats: { total: number; folderCount: number } | null;
}

/** 账号信息合并卡片：登录状态 / 平台主人身份 / 收藏夹概览（本地库实时统计） */
export const AccountInfoCards: React.FC<AccountInfoCardsProps> = ({ account, localStats }) => (
  <div className="bg-white dark:bg-[#161B26] p-4 sm:p-5 rounded-2xl border border-slate-200/80 dark:border-slate-800 shadow-2xs">
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 md:gap-0 md:divide-x md:divide-slate-100 dark:md:divide-slate-800">
      {/* Status card */}
      <div className="md:pr-5">
        <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">当前账号状态</span>
        <div className="mt-2 flex items-center justify-between">
          <div>
            {account.status === 'active' ? (
              <span className="inline-flex items-center gap-1.5 text-sm font-bold text-emerald-700 dark:text-emerald-400">
                <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                已启用 (登录有效)
              </span>
            ) : account.status === 'expired' ? (
              <span className="inline-flex items-center gap-1.5 text-sm font-bold text-amber-700 dark:text-amber-400">
                <AlertTriangle className="w-4 h-4 text-amber-600" />
                登录已过期 (需重新扫码)
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 text-sm font-bold text-slate-500 dark:text-slate-400">
                <Ban className="w-4 h-4 text-slate-400" />
                已禁用
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Identity & Owner card */}
      <div className="md:px-5">
        <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">平台主人身份</span>
        <div className="mt-2 flex items-center gap-3">
          {account.ownerAvatar ? (
            <img
              src={account.ownerAvatar}
              alt={account.ownerNickname || ''}
              className="w-10 h-10 rounded-full border-2 border-slate-100 dark:border-slate-800 object-cover"
              referrerPolicy="no-referrer"
            />
          ) : (
            <div className="w-10 h-10 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 font-bold flex items-center justify-center text-sm">
              ID
            </div>
          )}
          <div>
            <div className="text-sm font-bold text-slate-900 dark:text-white">
              {account.ownerNickname || '未绑定/未登录'}
            </div>
            <div className="text-xs text-slate-500 dark:text-slate-400 font-mono">
              UID: {account.ownerUid || '—'}
            </div>
          </div>
        </div>
      </div>

      {/* Usage & Folders card */}
      <div className="md:pl-5">
        <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">收藏夹概览</span>
        <div className="mt-2 flex items-center justify-between">
          <span className="text-2xl font-extrabold text-slate-900 dark:text-white">
            {localStats
              ? localStats.total
              : account.folders
                ? account.folders.reduce((acc, f) => acc + f.count, 0)
                : 0}
          </span>
        </div>
      </div>
    </div>
  </div>
);
