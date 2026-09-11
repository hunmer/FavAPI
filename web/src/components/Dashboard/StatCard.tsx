import React, { useEffect, useRef, useState } from 'react';
import { LucideIcon } from 'lucide-react';

interface StatCardProps {
  title: string;
  value: string | number;
  subtitle: string;
  icon: LucideIcon;
  iconColor: string;
  iconBg: string;
  trend?: {
    text: string;
    isPositive: boolean;
  };
}

/** 数字滚动（Corporate 克制版：400ms ease-out cubic；尊重系统"减少动态效果"）。 */
function useCountUp(target: number, duration = 400): number {
  const [display, setDisplay] = useState(0);
  const prev = useRef(0);

  useEffect(() => {
    const from = prev.current;
    prev.current = target;
    if (from === target) return;
    if (typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setDisplay(target);
      return;
    }
    const start = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const p = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - p, 3); // ease-out-cubic 减速收尾
      setDisplay(Math.round(from + (target - from) * eased));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, duration]);

  return display;
}

export const StatCard: React.FC<StatCardProps> = ({
  title,
  value,
  subtitle,
  icon: Icon,
  iconColor,
  iconBg,
  trend,
}) => {
  const numeric = typeof value === 'number' ? value : null;
  const animated = useCountUp(numeric ?? 0);

  return (
    <div className="bg-white dark:bg-[#161B26] rounded-3xl p-5 border border-slate-100 dark:border-slate-800 shadow-sm hover:shadow-md dark:hover:shadow-slate-950/40 transition-all duration-200 flex flex-col justify-between group">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">{title}</span>
        <div className={`w-10 h-10 rounded-2xl ${iconBg} ${iconColor} flex items-center justify-center transition-transform group-hover:scale-105 duration-200`}>
          <Icon className="w-5 h-5" />
        </div>
      </div>

      <div className="mt-4 flex flex-col">
        <div className="flex items-baseline gap-2">
          <span className="text-2xl lg:text-3xl font-extrabold text-slate-900 dark:text-white tracking-tight">
            {numeric !== null ? animated.toLocaleString() : value}
          </span>
          {trend && (
            <span
              className={`text-[11px] font-bold px-1.5 py-0.5 rounded-full ${
                trend.isPositive
                  ? 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800/60'
                  : 'bg-rose-50 dark:bg-rose-950/60 text-rose-600 dark:text-rose-400 border border-rose-200 dark:border-rose-800/60'
              }`}
            >
              {trend.text}
            </span>
          )}
        </div>
        <span className="text-xs text-slate-400 dark:text-slate-400 mt-1 font-medium">{subtitle}</span>
      </div>
    </div>
  );
};
