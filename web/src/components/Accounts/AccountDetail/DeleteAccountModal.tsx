import React from 'react';
import { Account } from '../../../types';

interface DeleteAccountModalProps {
  account: Account;
  onClose: () => void;
  onDelete: (account: Account) => void;
}

/** 删除账号确认弹窗：连同浏览器 Profile 一起删除，已入库收藏元数据保留 */
export const DeleteAccountModal: React.FC<DeleteAccountModalProps> = ({ account, onClose, onDelete }) => (
  <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
    <div className="anim-modal-enter bg-white dark:bg-[#161B26] w-full max-w-md rounded-[28px] p-6 shadow-2xl border border-slate-100 dark:border-slate-800 space-y-4">
      <h3 className="text-lg font-bold text-slate-900 dark:text-white">确认删除账号？</h3>
      <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
        此操作将删除账号 <strong className="text-slate-800 dark:text-slate-200">{account.name}</strong> 及其关联的收藏关系与本地 Chromium Profile 目录（{account.browserProfilePath}）。已入库的收藏元数据不会被抹除。
      </p>
      <div className="flex justify-end gap-2 pt-2">
        <button
          type="button"
          onClick={onClose}
          className="px-4 py-2 text-xs font-semibold text-slate-600 dark:text-slate-300 hover:text-slate-800 dark:hover:text-slate-100 rounded-xl"
        >
          取消
        </button>
        <button
          type="button"
          onClick={() => {
            onClose();
            onDelete(account);
          }}
          className="px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold rounded-xl shadow-xs"
        >
          确认删除
        </button>
      </div>
    </div>
  </div>
);
