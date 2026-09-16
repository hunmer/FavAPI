import React from 'react';
import { Account } from '../../../types';
import { AlertTriangle, Ban, CheckCircle2 } from 'lucide-react';

interface AccountInfoCardsProps {
  account: Account;
  localStats: { total: number; folderCount: number } | null;
}

/** 账号信息三卡片：登录状态 / 平台主人身份 / 收藏夹概览（本地库实时统计） */
export const AccountInfoCards: React.FC<AccountInfoCardsProps> = ({ account, localStats }) => (
  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
    {/* Status card */}
    <div className="bg-white p-4 sm:p-5 rounded-2xl border border-slate-200/80 shadow-2xs">
      <span className="text-xs font-semibold text-slate-500">当前账号状态</span>
      <div className="mt-2 flex items-center justify-between">
        <div>
          {account.status === 'active' ? (
            <span className="inline-flex items-center gap-1.5 text-sm font-bold text-emerald-700">
              <CheckCircle2 className="w-4 h-4 text-emerald-600" />
              已启用 (登录有效)
            </span>
          ) : account.status === 'expired' ? (
            <span className="inline-flex items-center gap-1.5 text-sm font-bold text-amber-700">
              <AlertTriangle className="w-4 h-4 text-amber-600" />
              登录已过期 (需重新扫码)
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 text-sm font-bold text-slate-500">
              <Ban className="w-4 h-4 text-slate-400" />
              已禁用
            </span>
          )}
        </div>
        <span className="text-[11px] text-slate-400">ID: {account.id}</span>
      </div>
      <p className="text-[11px] text-slate-400 mt-2">
        最后登录：{account.lastLoginTime}
      </p>
    </div>

    {/* Identity & Owner card */}
    <div className="bg-white p-4 sm:p-5 rounded-2xl border border-slate-200/80 shadow-2xs">
      <span className="text-xs font-semibold text-slate-500">平台主人身份</span>
      <div className="mt-2 flex items-center gap-3">
        {account.ownerAvatar ? (
          <img
            src={account.ownerAvatar}
            alt={account.ownerNickname || ''}
            className="w-10 h-10 rounded-full border-2 border-slate-100 object-cover"
            referrerPolicy="no-referrer"
          />
        ) : (
          <div className="w-10 h-10 rounded-full bg-slate-100 text-slate-600 font-bold flex items-center justify-center text-sm">
            ID
          </div>
        )}
        <div>
          <div className="text-sm font-bold text-slate-900">
            {account.ownerNickname || '未绑定/未登录'}
          </div>
          <div className="text-xs text-slate-500 font-mono">
            UID: {account.ownerUid || '—'}
          </div>
        </div>
      </div>
    </div>

    {/* Usage & Folders card */}
    <div className="bg-white p-4 sm:p-5 rounded-2xl border border-slate-200/80 shadow-2xs">
      <span className="text-xs font-semibold text-slate-500">收藏夹概览</span>
      <div className="mt-2 flex items-center justify-between">
        <span className="text-2xl font-extrabold text-slate-900">
          {localStats
            ? localStats.total
            : account.folders
              ? account.folders.reduce((acc, f) => acc + f.count, 0)
              : 0}
          <span className="text-xs font-normal text-slate-500 ml-1">件收藏内容（本地库）</span>
        </span>
        <span className="text-xs font-bold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded-full">
          {localStats ? localStats.folderCount : account.folders?.length || 0} 个收藏夹
        </span>
      </div>
      <p className="text-[11px] text-slate-400 mt-2">
        最近抓取使用：{account.lastUsedTime}
      </p>
    </div>
  </div>
);
