import React, { useState } from 'react';
import { Account } from '../../../types';
import { PlatformMeta } from '../../../data/platforms';
import {
  ArrowLeft,
  Ban,
  Cookie,
  Eraser,
  Monitor,
  MoreVertical,
  ShieldCheck,
  Trash2,
} from 'lucide-react';

interface AccountDetailHeaderProps {
  account: Account;
  platform: PlatformMeta;
  onBack: () => void;
  onOpenCookiesModal: (account: Account) => void;
  onCheckHealth: (account: Account) => void;
  onToggleStatus: (account: Account) => void;
  onToggleBrowser: (account: Account) => void;
  onRequestClearFavorites: () => void;
  onRequestDeleteAccount: () => void;
}

/** 账号详情顶栏：返回按钮、标题与账号操作工具栏（登录态/浏览器/启停/更多菜单） */
export const AccountDetailHeader: React.FC<AccountDetailHeaderProps> = ({
  account,
  platform,
  onBack,
  onOpenCookiesModal,
  onCheckHealth,
  onToggleStatus,
  onToggleBrowser,
  onRequestClearFavorites,
  onRequestDeleteAccount,
}) => {
  const [showActionMenu, setShowActionMenu] = useState(false);

  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-2 border-b border-slate-200/80 dark:border-slate-800">
      <div className="flex items-center gap-3">
        {account.platform !== 'wechat' && <button
          type="button"
          onClick={onBack}
          className="p-2 rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors shadow-2xs"
          title="返回账号列表"
        >
          <ArrowLeft className="w-4 h-4" />
        </button>}
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
              {account.name}
            </h2>
            <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold border ${platform.badgeBg}`}>
              {platform.name}
            </span>
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            最后登录：{account.lastLoginTime} · 最近抓取：{account.lastUsedTime}
          </p>
        </div>
      </div>

      {/* Action button toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        {/* Health check */}
        {account.platform !== 'wechat' && <button
          type="button"
          onClick={() => onCheckHealth(account)}
          className="px-3 py-1.5 rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700 text-xs font-semibold shadow-2xs inline-flex items-center gap-1.5 transition-colors"
          title="验证当前登录态有效性"
        >
          <ShieldCheck className="w-3.5 h-3.5 text-indigo-600" />
          登录态检查
        </button>}

        {/* Open/Close Browser */}
        <button
          type="button"
          onClick={() => onToggleBrowser(account)}
          className={`px-3 py-1.5 rounded-xl border text-xs font-semibold shadow-2xs inline-flex items-center gap-1.5 transition-colors ${
            'bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700'
          }`}
          title="以该账号独立 Profile 打开/关闭可视化 Chromium 浏览器"
        >
          <Monitor className="w-3.5 h-3.5" />
          打开浏览器
        </button>

        {/* More actions menu (dots) */}
        <div className="relative">
          <button
            type="button"
            onClick={() => setShowActionMenu((v) => !v)}
            className="p-2 rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700 shadow-2xs transition-colors"
            title="更多操作"
          >
            <MoreVertical className="w-3.5 h-3.5" />
          </button>

          {showActionMenu && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setShowActionMenu(false)} />
              <div className="absolute right-0 mt-2 w-44 bg-white dark:bg-[#161B26] rounded-2xl shadow-xl border border-slate-200 dark:border-slate-700 py-1.5 z-50 anim-modal-enter">
                <button
                  type="button"
                  onClick={() => {
                    setShowActionMenu(false);
                    onOpenCookiesModal(account);
                  }}
                  className="w-full px-4 py-2 text-left text-xs font-semibold text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800 inline-flex items-center gap-2 transition-colors"
                >
                  <Cookie className="w-3.5 h-3.5 text-amber-600" />
                  查看 Cookies
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setShowActionMenu(false);
                    onToggleStatus(account);
                  }}
                  className="w-full px-4 py-2 text-left text-xs font-semibold text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800 inline-flex items-center gap-2 transition-colors"
                >
                  <Ban className="w-3.5 h-3.5 text-slate-500" />
                  {account.status === 'disabled' ? '启用账号' : '禁用账号'}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setShowActionMenu(false);
                    onRequestClearFavorites();
                  }}
                  className="w-full px-4 py-2 text-left text-xs font-semibold text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800 inline-flex items-center gap-2 transition-colors"
                >
                  <Eraser className="w-3.5 h-3.5 text-amber-600" />
                  清空收藏夹
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setShowActionMenu(false);
                    onRequestDeleteAccount();
                  }}
                  className="w-full px-4 py-2 text-left text-xs font-semibold text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950 inline-flex items-center gap-2 transition-colors"
                >
                  <Trash2 className="w-3.5 h-3.5 text-rose-500" />
                  删除账号
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
