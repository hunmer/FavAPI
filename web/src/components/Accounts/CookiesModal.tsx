import React, { useState, useEffect } from 'react';
import { X, Cookie, Copy, Check, Shield, RefreshCw } from 'lucide-react';
import { Account, CookieItem } from '../../types';
import * as api from '../../api';

interface CookiesModalProps {
  account: Account;
  onClose: () => void;
}

export const CookiesModal: React.FC<CookiesModalProps> = ({ account, onClose }) => {
  const [copied, setCopied] = useState(false);
  const [cookies, setCookies] = useState<CookieItem[] | null>(null);
  const [error, setError] = useState('');

  const load = async () => {
    setCookies(null);
    setError('');
    try {
      setCookies(await api.getCookieItems(account.id));
    } catch (e: any) {
      setError(e.message);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [account.id]);

  const handleCopyJSON = () => {
    if (!cookies) return;
    navigator.clipboard.writeText(JSON.stringify(cookies, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div
      id="cookies-modal-backdrop"
      className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 anim-backdrop-enter"
      onClick={onClose}
    >
      <div
        id="cookies-modal"
        onClick={(e) => e.stopPropagation()}
        className="anim-modal-enter bg-white dark:bg-[#161B26] w-full max-w-2xl rounded-[32px] shadow-2xl border border-slate-100 dark:border-slate-800 overflow-hidden flex flex-col max-h-[85vh]"
      >
        {/* Header */}
        <div className="p-5 sm:p-6 bg-slate-50 dark:bg-slate-800 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-amber-100 dark:bg-amber-950 text-amber-800 dark:text-amber-400 flex items-center justify-center shadow-xs">
              <Cookie className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base sm:text-lg font-bold text-slate-900 dark:text-white">
                浏览器会话 Cookies 查看
              </h3>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                账号: {account.name} • 自动存库加密持久化
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="w-8 h-8 rounded-full bg-white dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600 text-slate-700 dark:text-slate-200 flex items-center justify-center transition-colors shadow-2xs"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content Table */}
        <div className="p-6 overflow-y-auto space-y-4">
          {error ? (
            <div className="p-8 text-center space-y-3">
              <p className="text-xs text-rose-600">{error}</p>
              <button
                type="button"
                onClick={load}
                className="px-4 py-2 bg-slate-900 dark:bg-slate-700 text-white text-xs font-bold rounded-xl inline-flex items-center gap-1.5"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                重试读取
              </button>
            </div>
          ) : cookies === null ? (
            <div className="py-12 flex flex-col items-center gap-3 text-slate-400">
              <RefreshCw className="w-6 h-6 animate-spin" />
              <p className="text-xs">正在打开浏览器 Profile 读取 Cookies...</p>
            </div>
          ) : (
            <>
              <div className="bg-amber-50/70 dark:bg-amber-950/60 text-amber-900 dark:text-amber-300 text-xs p-3 rounded-2xl border border-amber-200/60 dark:border-amber-800 flex items-center justify-between">
                <span className="flex items-center gap-1.5">
                  <Shield className="w-4 h-4 text-amber-600" />
                  Cookies 仅在私有化部署实例内部调用，已与本地 Profile 关联同步。
                </span>
                <span className="font-bold text-[11px] bg-amber-100 dark:bg-amber-900 px-2 py-0.5 rounded-full">
                  共 {cookies.length} 条项
                </span>
              </div>

              <div className="border border-slate-200 dark:border-slate-700 rounded-2xl overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead>
                      <tr className="bg-slate-50 dark:bg-slate-800 text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-700 font-semibold">
                        <th className="py-2.5 px-3">Cookie 名称</th>
                        <th className="py-2.5 px-3">Cookie 值 (缩略)</th>
                        <th className="py-2.5 px-3">Domain 域名</th>
                        <th className="py-2.5 px-3">过期时间</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 dark:divide-slate-800 font-mono">
                      {cookies.map((c, i) => (
                        <tr key={i} className="hover:bg-slate-50/80 dark:hover:bg-slate-800/60 transition-colors">
                          <td className="py-2.5 px-3 font-semibold text-slate-900 dark:text-white">
                            {c.name}
                          </td>
                          <td className="py-2.5 px-3 text-slate-600 dark:text-slate-300 max-w-[150px] truncate" title={c.value}>
                            {c.value.length > 16 ? `${c.value.slice(0, 16)}...` : c.value || '—'}
                          </td>
                          <td className="py-2.5 px-3 text-slate-500 dark:text-slate-400">{c.domain}</td>
                          <td className="py-2.5 px-3 text-slate-500 dark:text-slate-400 whitespace-nowrap">{c.expires}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 sm:p-5 bg-slate-50 dark:bg-slate-800 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between">
          <button
            type="button"
            onClick={handleCopyJSON}
            disabled={!cookies}
            className="text-xs font-bold text-slate-700 dark:text-slate-200 hover:text-slate-900 dark:hover:text-white px-4 py-2 rounded-xl bg-white dark:bg-slate-700 border border-slate-200 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-600 transition-colors inline-flex items-center gap-1.5 disabled:opacity-50"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
            {copied ? '已复制 JSON' : '复制为 JSON'}
          </button>

          <button
            type="button"
            onClick={onClose}
            className="px-5 py-2 bg-slate-900 hover:bg-slate-800 dark:bg-slate-700 dark:hover:bg-slate-600 text-white text-xs font-bold rounded-xl shadow-xs"
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  );
};
