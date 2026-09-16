import React, { useState } from 'react';
import { Account } from '../../../types';
import { clearFavorites } from '../../../api';
import { RefreshCw } from 'lucide-react';

interface ClearFavoritesModalProps {
  account: Account;
  localStats: { total: number; folderCount: number } | null;
  onClose: () => void;
  onFavoritesCleared: (account: Account) => void;
}

/** 清空收藏夹确认弹窗：删除本地库中该账号的全部收藏关系（云端不受影响） */
export const ClearFavoritesModal: React.FC<ClearFavoritesModalProps> = ({
  account,
  localStats,
  onClose,
  onFavoritesCleared,
}) => {
  const [isClearing, setIsClearing] = useState(false);
  const [clearError, setClearError] = useState<string | null>(null);

  const handleClearFavorites = async () => {
    setIsClearing(true);
    setClearError(null);
    try {
      await clearFavorites(account.id);
      onClose();
      onFavoritesCleared(account);
    } catch (e) {
      setClearError(e instanceof Error ? e.message : String(e));
    } finally {
      setIsClearing(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="anim-modal-enter bg-white w-full max-w-md rounded-[28px] p-6 shadow-2xl border border-slate-100 space-y-4">
        <h3 className="text-lg font-bold text-slate-900">确认清空收藏夹？</h3>
        <p className="text-xs text-slate-500 leading-relaxed">
          将删除 <strong className="text-slate-800">{account.name}</strong> 在本地库中的全部收藏关系（共{' '}
          {localStats ? localStats.total : 0} 件）。平台云端收藏不受影响，可随时重新抓取恢复。
        </p>
        {clearError && (
          <p className="text-xs text-rose-600 bg-rose-50 p-2 rounded-xl">{clearError}</p>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            disabled={isClearing}
            onClick={onClose}
            className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-800 rounded-xl disabled:opacity-50"
          >
            取消
          </button>
          <button
            type="button"
            disabled={isClearing}
            onClick={handleClearFavorites}
            className="px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white text-xs font-bold rounded-xl shadow-xs disabled:opacity-50 inline-flex items-center gap-1.5"
          >
            {isClearing && <RefreshCw className="w-3 h-3 animate-spin" />}
            {isClearing ? '清空中...' : '确认清空'}
          </button>
        </div>
      </div>
    </div>
  );
};
