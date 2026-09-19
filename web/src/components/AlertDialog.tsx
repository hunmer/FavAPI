import React, { useEffect, useRef, useSyncExternalStore } from 'react';
import { AlertTriangle, Info } from 'lucide-react';

/**
 * 全局 Alert / Confirm 弹窗（替代原生 alert / window.confirm）。
 * 命令式调用：`await confirmDialog({...})` / `await alertDialog({...})`，
 * 由挂在 App 根部的 <AlertDialogHost /> 负责渲染。
 */

interface DialogRequest {
  id: number;
  title: string;
  message?: string;
  confirmText: string;
  cancelText?: string;
  danger: boolean;
  resolve: (ok: boolean) => void;
}

let current: DialogRequest | null = null;
let nextId = 1;
const listeners = new Set<() => void>();

const emit = () => listeners.forEach((l) => l());
const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => listeners.delete(l);
};

const open = (req: Omit<DialogRequest, 'id' | 'resolve'>): Promise<boolean> => {
  // 前一个弹窗未关闭时先以「取消」收尾，避免 Promise 悬挂
  current?.resolve(false);
  return new Promise<boolean>((resolve) => {
    current = { ...req, id: nextId++, resolve };
    emit();
  });
};

export function confirmDialog(opts: {
  title: string;
  message?: string;
  confirmText?: string;
  cancelText?: string;
  danger?: boolean;
}): Promise<boolean> {
  return open({
    title: opts.title,
    message: opts.message,
    confirmText: opts.confirmText || '确定',
    cancelText: opts.cancelText || '取消',
    danger: !!opts.danger,
  });
}

export function alertDialog(opts: {
  title: string;
  message?: string;
  confirmText?: string;
}): Promise<void> {
  return open({
    title: opts.title,
    message: opts.message,
    confirmText: opts.confirmText || '知道了',
    danger: false,
  }).then(() => undefined);
}

export const AlertDialogHost: React.FC = () => {
  const req = useSyncExternalStore(subscribe, () => current);
  const confirmBtnRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!req) return;
    confirmBtnRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        settle(false);
      } else if (e.key === 'Enter' && !(e.target instanceof HTMLButtonElement)) {
        // 焦点已在按钮上时交给原生 click，避免取消/确认同时触发
        e.preventDefault();
        settle(true);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [req?.id]);

  if (!req) return null;

  const settle = (ok: boolean) => {
    current = null;
    emit();
    req.resolve(ok);
  };

  return (
    <div
      className="fixed inset-0 z-[70] bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 anim-backdrop-enter"
      onClick={() => settle(false)}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        role="alertdialog"
        aria-modal="true"
        className="anim-modal-enter relative bg-white dark:bg-[#161B26] w-full max-w-sm rounded-3xl shadow-2xl border border-slate-100 dark:border-slate-800 p-6"
      >
        <div className="flex items-start gap-3">
          {req.danger ? (
            <AlertTriangle className="w-5 h-5 text-rose-500 shrink-0 mt-0.5" />
          ) : (
            <Info className="w-5 h-5 text-sky-500 shrink-0 mt-0.5" />
          )}
          <div className="min-w-0">
            <h3 className="text-sm font-bold text-slate-900 dark:text-white">{req.title}</h3>
            {req.message && (
              <p className="mt-1.5 text-xs leading-relaxed text-slate-500 dark:text-slate-400 whitespace-pre-wrap">
                {req.message}
              </p>
            )}
          </div>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          {req.cancelText && (
            <button
              type="button"
              onClick={() => settle(false)}
              className="px-4 py-2 rounded-xl bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300 text-xs font-semibold transition-colors cursor-pointer"
            >
              {req.cancelText}
            </button>
          )}
          <button
            ref={confirmBtnRef}
            type="button"
            onClick={() => settle(true)}
            className={`px-4 py-2 rounded-xl text-white text-xs font-bold shadow-xs transition-colors cursor-pointer ${
              req.danger
                ? 'bg-rose-600 hover:bg-rose-500'
                : 'bg-violet-600 hover:bg-violet-500'
            }`}
          >
            {req.confirmText}
          </button>
        </div>
      </div>
    </div>
  );
};
