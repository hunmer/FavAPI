import React, { useState } from 'react';
import { ChevronDown, User } from 'lucide-react';

export interface DropdownSelectOption {
  id: string;
  label: string;
  icon?: React.ReactNode;
  /** 显示在标签后的计数，如 `账号名 (12)`；不传则不显示 */
  count?: number;
}

interface DropdownSelectProps {
  options: DropdownSelectOption[];
  value: string;
  onChange: (id: string) => void;
  /** 附加到最外层容器的类名（如 `w-44` 控宽），全宽场景可不传 */
  className?: string;
}

const labelOf = (o: DropdownSelectOption) => (o.count != null ? `${o.label} (${o.count})` : o.label);

/** 自定义下拉选择器（触发按钮 + 展开列表），替代原生 select 以统一风格；icon 缺省回退 User 图标 */
export const DropdownSelect: React.FC<DropdownSelectProps> = ({ options, value, onChange, className = '' }) => {
  const [open, setOpen] = useState(false);
  const selected = options.find((o) => o.id === value) ?? options[0];
  return (
    <div className={`rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 overflow-hidden ${className}`}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full px-3 py-2 flex items-center justify-between gap-2 text-xs font-medium text-slate-800 dark:text-slate-200 cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
      >
        <span className="flex items-center gap-1.5 min-w-0">
          {selected?.icon ?? <User className="w-3.5 h-3.5 text-slate-400 shrink-0" />}
          <span className="truncate">{selected ? labelOf(selected) : '全部'}</span>
        </span>
        <ChevronDown className={`w-3.5 h-3.5 text-slate-400 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="border-t border-slate-100 dark:border-slate-700 max-h-52 overflow-y-auto bg-white dark:bg-slate-800">
          {options.map((o) => (
            <button
              key={o.id}
              type="button"
              onClick={() => {
                onChange(o.id);
                setOpen(false);
              }}
              className={`w-full px-3 py-2 flex items-center gap-1.5 text-xs cursor-pointer transition-colors ${
                o.id === value
                  ? 'bg-violet-50 dark:bg-violet-950 text-violet-700 dark:text-violet-400 font-semibold'
                  : 'text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700'
              }`}
            >
              {o.icon ?? <User className="w-3.5 h-3.5 text-slate-400 shrink-0" />}
              <span className="truncate">{labelOf(o)}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
