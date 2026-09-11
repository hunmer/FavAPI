import React, { useEffect, useState } from 'react';
import { X, Plus, AlertCircle, Sparkles, Check } from 'lucide-react';
import { PlatformId } from '../../types';
import { listPlatforms, PlatformInfoRow } from '../../api';

interface CreateAccountModalProps {
  onClose: () => void;
  onCreate: (name: string, platform: PlatformId) => void;
}

export const CreateAccountModal: React.FC<CreateAccountModalProps> = ({
  onClose,
  onCreate,
}) => {
  const [platforms, setPlatforms] = useState<PlatformInfoRow[]>([]);
  const [selectedPlatform, setSelectedPlatform] = useState<PlatformId | ''>('');
  const [accountName, setAccountName] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    listPlatforms()
      .then((items) => {
        const available = items.filter((p) => p.implemented && p.supported_actions.includes('list_favorites'));
        setPlatforms(available);
        if (available.length) setSelectedPlatform((current) => current || available[0].platform);
      })
      .catch((e) => setError(`平台列表加载失败：${e.message}`));
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!accountName.trim()) {
      setError('请输入账号备注名称');
      return;
    }
    if (!selectedPlatform) {
      setError('暂无可用平台');
      return;
    }
    onCreate(accountName.trim(), selectedPlatform);
    onClose();
  };

  return (
    <div
      id="create-account-modal-backdrop"
      className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 anim-backdrop-enter"
      onClick={onClose}
    >
      <div
        id="create-account-modal"
        onClick={(e) => e.stopPropagation()}
        className="anim-modal-enter bg-white w-full max-w-lg rounded-[28px] shadow-2xl border border-slate-100 overflow-hidden flex flex-col"
      >
        {/* Header */}
        <div className="p-5 sm:p-6 bg-slate-50 border-b border-slate-100 flex items-center justify-between">
          <div>
            <h3 className="text-lg font-bold text-slate-900">创建新抓取账号</h3>
            <p className="text-xs text-slate-500 mt-0.5">
              选择目标平台并设置名称，创建后可通过桌面浏览器窗口扫码登录
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="w-8 h-8 rounded-full bg-white hover:bg-slate-200 text-slate-700 flex items-center justify-center transition-colors shadow-2xs"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-6 space-y-5">
          {/* Platform selection grid */}
          <div>
            <label className="block text-xs font-bold text-slate-700 mb-2 uppercase tracking-wider">
              选择目标平台 <span className="text-red-500">*</span>
            </label>
            <div className="grid grid-cols-2 sm:grid-cols-2 gap-2.5">
              {platforms.map((p) => {
                const isSelected = selectedPlatform === p.platform;
                return (
                  <button
                    key={p.platform}
                    type="button"
                    disabled={!p.implemented}
                    onClick={() => {
                      if (p.implemented) {
                        setSelectedPlatform(p.platform);
                        setError('');
                      }
                    }}
                    className={`relative p-3 rounded-2xl border text-left transition-all ${
                      isSelected
                        ? 'border-indigo-600 bg-indigo-50/40 ring-2 ring-indigo-500/20'
                        : 'border-slate-200 hover:border-slate-300 hover:bg-slate-50'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-bold text-slate-900">{p.display_name}</span>
                      {isSelected ? (
                        <span className="w-4 h-4 rounded-full bg-indigo-600 text-white flex items-center justify-center text-[10px]">
                          <Check className="w-2.5 h-2.5 stroke-[3]" />
                        </span>
                      ) : null}
                    </div>
                    <p className="text-[11px] text-slate-500 line-clamp-1">支持操作：{p.supported_actions.join('、')}</p>
                  </button>
                );
              })}
              {!platforms.length && <p className="col-span-2 text-xs text-slate-500">暂无可用平台</p>}
            </div>
          </div>

          {/* Account name */}
          <div>
            <label className="block text-xs font-bold text-slate-700 mb-1.5 uppercase tracking-wider">
              账号备注名称 <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={accountName}
              onChange={(e) => {
                setAccountName(e.target.value);
                setError('');
              }}
              placeholder="例如：我的抖音主号、B站主力收藏号"
              className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900"
            />
            {error && (
              <p className="text-xs text-rose-600 mt-1 flex items-center gap-1">
                <AlertCircle className="w-3.5 h-3.5" />
                {error}
              </p>
            )}
          </div>

          <div className="bg-amber-50/70 p-3 rounded-xl border border-amber-200/60 text-xs text-amber-800 flex items-start gap-2">
            <Sparkles className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
            <span>创建后，服务将为该账号分配专属独立的浏览器 Profile 隔离目录，确保 Cookies 与多账号登录态互不干扰。</span>
          </div>

          {/* Buttons */}
          <div className="pt-2 flex items-center justify-end gap-2.5">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-800 rounded-xl"
            >
              取消
            </button>
            <button
              type="submit"
              className="px-5 py-2.5 bg-slate-900 hover:bg-slate-800 text-white text-xs sm:text-sm font-bold rounded-xl shadow-xs flex items-center gap-1.5 transition-transform active:scale-98"
            >
              <Plus className="w-4 h-4" />
              立即创建
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
