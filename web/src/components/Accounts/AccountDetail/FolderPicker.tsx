import React from 'react';
import { Account } from '../../../types';
import { FolderHeart } from 'lucide-react';

interface FolderPickerProps {
  account: Account;
  selectedMediaId: string;
  onSelect: (mediaId: string) => void;
}

/** 名下收藏夹预览网格：点击卡片直接设为抓取目标 */
export const FolderPicker: React.FC<FolderPickerProps> = ({ account, selectedMediaId, onSelect }) => {
  if (!account.folders || account.folders.length === 0) return null;

  return (
    <div className="bg-white p-4 sm:p-5 rounded-2xl border border-slate-200/80 shadow-2xs">
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider flex items-center gap-1.5">
          <FolderHeart className="w-4 h-4 text-indigo-600" />
          名下收藏夹与数量（点击直接设为抓取目标）
        </h4>
        <span className="text-[11px] text-slate-400">自动同步自平台接口</span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2.5">
        {account.folders.map((f) => {
          const isSelected = selectedMediaId === f.mediaId;
          return (
            <button
              key={f.id}
              type="button"
              onClick={() => onSelect(f.mediaId)}
              className={`p-3 rounded-xl border text-left transition-all ${
                isSelected
                  ? 'border-indigo-600 bg-indigo-50/50 ring-2 ring-indigo-500/20 shadow-2xs'
                  : 'border-slate-200 hover:border-slate-300 hover:bg-slate-50'
              }`}
            >
              <div className="flex items-center justify-between text-xs font-bold text-slate-900 mb-1">
                <span className="truncate">{f.name}</span>
                {f.isDefault && (
                  <span className="text-[9px] bg-slate-200 text-slate-700 px-1 rounded">默认</span>
                )}
              </div>
              <div className="text-xs text-slate-500 flex items-center justify-between">
                <span>{f.count} 件</span>
                <span className="font-mono text-[10px] text-slate-400">ID:{f.mediaId}</span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
};
