import React from 'react';

/** 视图模式：网格 / 瀑布流 / 列表（各页面共用，可只取子集） */
export type ViewMode = 'grid' | 'waterfall' | 'list';

export interface ViewModeOption<T extends string = ViewMode> {
  value: T;
  icon: React.ComponentType<{ className?: string }>;
  /** 悬浮提示与无障碍标签（按钮仅图标） */
  title: string;
}

/** 视图切换分段控件（仅图标，悬浮提示见 title）：模式集合由调用方传入 */
export const ViewModeSwitch = <T extends string>({
  modes,
  value,
  onChange,
}: {
  modes: ViewModeOption<T>[];
  value: T;
  onChange: (mode: T) => void;
}) => (
  <div className="bg-slate-100 dark:bg-slate-800 p-1 rounded-2xl border border-slate-200 dark:border-slate-700 flex items-center gap-1 shadow-2xs">
    {modes.map((m) => {
      const Icon = m.icon;
      const active = m.value === value;
      return (
        <button
          key={m.value}
          type="button"
          onClick={() => onChange(m.value)}
          title={m.title}
          aria-label={m.title}
          className={`p-2 rounded-xl transition-all cursor-pointer ${
            active
              ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-xs'
              : 'text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200'
          }`}
        >
          <Icon className="w-4 h-4" />
        </button>
      );
    })}
  </div>
);

/** 从 localStorage 读取记忆的视图模式，非法值回退 fallback */
export const readViewMode = (storageKey: string, fallback: ViewMode): ViewMode => {
  const saved = localStorage.getItem(storageKey);
  return saved === 'grid' || saved === 'waterfall' || saved === 'list' ? saved : fallback;
};
