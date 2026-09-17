import React, { useRef } from 'react';
import { uploadWechatJson } from '../../api';
import { Account } from '../../types';
import { PLATFORMS } from '../../data/platforms';
import { Play, ArrowUpRight, FolderHeart, CheckCircle2, AlertCircle, Clock, QrCode, User } from 'lucide-react';
import { SiteIcon, usePlatformInfo } from '../SiteIcon';

interface ActiveAccountCardProps {
  account: Account;
  onSelect: (acc: Account) => void;
  onQuickSync?: (acc: Account) => void;
  onLogin?: (acc: Account) => void;
}

export const ActiveAccountCard: React.FC<ActiveAccountCardProps> = ({
  account,
  onSelect,
  onQuickSync,
  onLogin,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  // mock 未收录的平台（如 threads）回退到后端 /platforms 的 display_name 与中性样式
  const platformMeta = PLATFORMS.find((p) => p.id === account.platform);
  const backendInfo = usePlatformInfo(account.platform);
  const platformName = platformMeta?.name || backendInfo?.display_name || account.platform;
  const badgeBg = platformMeta?.badgeBg || 'bg-slate-100 text-slate-600 border-slate-200';
  const totalFoldersCount = account.folders?.reduce((acc, f) => acc + f.count, 0) || 0;
  // last_login_at 为空（fmtDateTime 映射为 '—'）表示从未扫码登录，即未绑定账号
  const notLoggedIn = !account.lastLoginTime || account.lastLoginTime === '—';
  const isWeChat = account.platform === 'wechat';

  return (
    <div className="bg-white dark:bg-[#161B26] rounded-3xl p-5 border border-slate-100 dark:border-slate-800 shadow-sm hover:shadow-md dark:hover:shadow-slate-950/40 transition-all flex flex-col justify-between group">
      <div>
        {/* Top bar: Platform badge & Status */}
        <div className="flex items-center justify-between gap-2 mb-3">
          <div className="flex items-center gap-2">
            <span
              className={`inline-flex items-center gap-1 text-[11px] font-bold px-2.5 py-1 rounded-full border ${badgeBg}`}
            >
              <SiteIcon platform={account.platform} name={platformName} className="w-3.5 h-3.5" />
              {platformName.split(' ')[0]}
            </span>
            <span className="text-[11px] text-slate-400 dark:text-slate-400 font-mono">
              UID: {account.ownerUid || '38819201'}
            </span>
          </div>

          <div className="flex items-center gap-1.5 text-xs font-semibold">
            {isWeChat || account.status === 'active' ? (
              <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
                <CheckCircle2 className="w-3.5 h-3.5" />
                会话有效
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-rose-500 dark:text-rose-400">
                <AlertCircle className="w-3.5 h-3.5" />
                需要续期
              </span>
            )}
          </div>
        </div>

        {/* Account Info */}
        <div className="flex items-center gap-3.5 my-3">
          {account.ownerAvatar ? (
            <img
              src={account.ownerAvatar}
              alt={account.name}
              className="w-12 h-12 rounded-2xl object-cover ring-2 ring-slate-100 dark:ring-slate-800 shrink-0"
            />
          ) : (
            <div className="w-12 h-12 rounded-2xl bg-slate-100 dark:bg-slate-800 flex items-center justify-center ring-2 ring-slate-100 dark:ring-slate-800 shrink-0">
              <User className="w-6 h-6 text-slate-400" />
            </div>
          )}
          <div className="min-w-0">
            <h4 className="text-sm font-bold text-slate-900 dark:text-white truncate group-hover:text-sky-600 dark:group-hover:text-sky-400 transition-colors">
              {account.name}
            </h4>
            <div className="text-xs text-slate-500 dark:text-slate-400 flex items-center gap-2 mt-0.5">
              <span>{account.ownerNickname || '已绑定用户'}</span>
              <span>•</span>
              <span className="flex items-center gap-1 text-slate-400 dark:text-slate-400">
                <FolderHeart className="w-3 h-3 text-sky-500" />
                {account.folders?.length || 1} 个收藏夹 ({totalFoldersCount} 条)
              </span>
            </div>
          </div>
        </div>

        {/* Sync Progress & Last Sync Time */}
        <div className="mt-4 pt-3 border-t border-slate-50 dark:border-slate-800/80">
          <div className="flex items-center justify-between text-[11px] text-slate-400 dark:text-slate-400 mb-1.5">
            <span className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              上次同步: {account.lastUsedTime}
            </span>
            <span className="font-semibold text-slate-600 dark:text-slate-300">100% 就绪</span>
          </div>
          <div className="w-full h-1.5 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{
                width: account.status === 'active' ? '100%' : '35%',
                backgroundColor: platformMeta?.color || '#94a3b8',
              }}
            />
          </div>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="mt-4 pt-3 flex items-center gap-2">
        <button
          onClick={() => (isWeChat ? fileInputRef.current?.click() : (notLoggedIn ? onLogin?.(account) : onQuickSync?.(account)))}
          className="flex-1 py-2 px-3 rounded-xl bg-slate-900 dark:bg-slate-800 text-white dark:text-slate-100 text-xs font-semibold hover:bg-slate-800 dark:hover:bg-slate-700 transition-all flex items-center justify-center gap-1.5 shadow-sm active:scale-95 border border-transparent dark:border-slate-700"
        >
          {isWeChat ? (
            <>导入 JSON</>
          ) : notLoggedIn ? (
            <>
              <QrCode className="w-3.5 h-3.5" />
              登录账号
            </>
          ) : (
            <>
              <Play className="w-3.5 h-3.5 fill-current" />
              进入主页
            </>
          )}
        </button>
        {isWeChat && <input ref={fileInputRef} type="file" accept=".json,application/json" className="hidden" onChange={async (e) => {
          const file = e.target.files?.[0]; if (!file) return;
          try { await uploadWechatJson(account.id, file); onSelect(account); } catch { /* 详情页可重试 */ }
          e.currentTarget.value = '';
        }} />}
        <button
          onClick={() => onSelect(account)}
          className="p-2 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white hover:bg-slate-200 dark:hover:bg-slate-700 transition-all border border-transparent dark:border-slate-700"
          title="打开专属工作台"
        >
          <ArrowUpRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
};
