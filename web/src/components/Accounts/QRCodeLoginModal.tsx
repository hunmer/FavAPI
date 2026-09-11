import React, { useState, useEffect, useRef, useCallback } from 'react';
import { X, QrCode, RefreshCw, CheckCircle2, AlertTriangle, Smartphone, ShieldCheck, Monitor } from 'lucide-react';
import { Account } from '../../types';
import { PLATFORMS } from '../../data/mockFavData';
import * as api from '../../api';

interface QRCodeLoginModalProps {
  account: Account;
  onClose: () => void;
  onLoginDone: (accountId: string, ok: boolean) => void;
}

export const QRCodeLoginModal: React.FC<QRCodeLoginModalProps> = ({
  account,
  onClose,
  onLoginDone,
}) => {
  // waiting: 等待用户在弹出的浏览器窗口中扫码；success / expired 为终态
  const [step, setStep] = useState<'starting' | 'waiting' | 'success' | 'expired'>('starting');
  const [errorMsg, setErrorMsg] = useState('');
  const [secondsLeft, setSecondsLeft] = useState(300); // 后端 LOGIN_TIMEOUT=300s
  const finishedRef = useRef(false);

  const platformMeta = PLATFORMS.find((p) => p.id === account.platform) || PLATFORMS[0];

  const finish = useCallback(
    (ok: boolean, message?: string) => {
      if (finishedRef.current) return;
      finishedRef.current = true;
      if (ok) {
        setStep('success');
        onLoginDone(account.id, true);
      } else {
        setErrorMsg(message || '超时未检测到扫码');
        setStep('expired');
        onLoginDone(account.id, false);
      }
    },
    [account.id, onLoginDone]
  );

  // 发起登录并轮询结果
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await api.startLogin(account.id);
        if (cancelled) return;
        setStep('waiting');
      } catch (e: any) {
        if (!cancelled) finish(false, e.message);
      }
    })();
    return () => {
      cancelled = true;
    };
  // 登录流程按账号实例只启动一次。父组件刷新账号列表会重渲染弹窗，不能因此重复调用 startLogin。
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [account.id]);

  // 倒计时
  useEffect(() => {
    if (step === 'success' || step === 'expired') return;
    const interval = setInterval(() => {
      setSecondsLeft((prev) => {
        if (prev <= 1) {
          finish(false, '二维码已超时');
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [step, finish]);

  const handleManualCheck = async () => {
    try {
      const s = await api.loginStatus(account.id);
      if (!s.busy && (s.logged_in || !s.logging_in)) {
        finish(!!s.logged_in, s.logged_in ? undefined : '未检测到登录态');
      }
    } catch (e: any) {
      finish(false, e.message);
    }
  };

  return (
    <div
      id="qr-login-modal-backdrop"
      className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4 anim-backdrop-enter"
      onClick={onClose}
    >
      <div
        id="qr-login-modal"
        onClick={(e) => e.stopPropagation()}
        className="anim-modal-enter bg-white w-full max-w-md rounded-[32px] shadow-2xl border border-slate-100 overflow-hidden flex flex-col"
      >
        {/* Header */}
        <div className="p-5 bg-slate-50 border-b border-slate-100 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-slate-900 text-white flex items-center justify-center">
              <QrCode className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-base font-bold text-slate-900">平台扫码登录</h3>
              <p className="text-xs text-slate-500">
                {account.name} • {platformMeta.name}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="w-8 h-8 rounded-full bg-white hover:bg-slate-200 text-slate-700 flex items-center justify-center transition-colors shadow-2xs"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 flex flex-col items-center text-center">
          {/* Browser Profile notification */}
          <div className="w-full bg-slate-100/70 py-1.5 px-3 rounded-xl text-[11px] text-slate-600 mb-5 flex items-center justify-center gap-1.5">
            <Monitor className="w-3.5 h-3.5 text-slate-500" />
            <span>已启动本地 Chromium 窗口并挂载隔离会话</span>
          </div>

          {step === 'starting' && (
            <div className="py-12 space-y-3">
              <RefreshCw className="w-8 h-8 text-indigo-600 animate-spin mx-auto" />
              <p className="text-sm font-semibold text-slate-800">
                正在启动浏览器环境...
              </p>
              <p className="text-xs text-slate-400">
                服务正在分配隔离的独立 Profile
              </p>
            </div>
          )}

          {step === 'waiting' && (
            <div className="space-y-4 flex flex-col items-center">
              {/* QR Code Container（真实二维码展示在弹出的浏览器窗口中，此处为引导示意） */}
              <div className="relative p-4 bg-white rounded-2xl border-2 border-slate-200/90 shadow-sm">
                <div className="w-48 h-48 bg-slate-900 rounded-xl p-2 flex items-center justify-center relative overflow-hidden">
                  <svg viewBox="0 0 100 100" className="w-full h-full text-white fill-current opacity-60">
                    <rect x="10" y="10" width="25" height="25" fill="white" />
                    <rect x="15" y="15" width="15" height="15" fill="#0f172a" />
                    <rect x="18" y="18" width="9" height="9" fill="white" />
                    <rect x="65" y="10" width="25" height="25" fill="white" />
                    <rect x="70" y="15" width="15" height="15" fill="#0f172a" />
                    <rect x="73" y="18" width="9" height="9" fill="white" />
                    <rect x="10" y="65" width="25" height="25" fill="white" />
                    <rect x="15" y="70" width="15" height="15" fill="#0f172a" />
                    <rect x="18" y="73" width="9" height="9" fill="white" />
                    <rect x="42" y="15" width="8" height="8" fill="white" />
                    <rect x="45" y="30" width="10" height="10" fill="white" />
                    <rect x="60" y="45" width="8" height="15" fill="white" />
                    <rect x="40" y="60" width="12" height="10" fill="white" />
                    <rect x="70" y="65" width="15" height="12" fill="white" />
                    <rect x="25" y="45" width="10" height="10" fill="white" />
                  </svg>
                  <div className="absolute inset-0 m-auto w-10 h-10 rounded-xl bg-white flex items-center justify-center shadow-md border border-slate-100">
                    <span className="text-[10px] font-bold text-slate-800">
                      {account.platform === 'bilibili' ? 'B站' : account.platform === 'xiaohongshu' ? '小红书' : '抖音'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Status text & Countdown */}
              <div>
                <p className="text-sm font-bold text-slate-800 flex items-center justify-center gap-1.5">
                  <Smartphone className="w-4 h-4 text-indigo-600" />
                  请在弹出的浏览器窗口中完成扫码
                </p>
                <p className="text-xs text-slate-400 mt-1">
                完成登录后点击下方按钮确认（{secondsLeft} 秒后超时）
                </p>
              </div>

              {/* Action */}
              <button
                type="button"
                onClick={handleManualCheck}
                className="text-xs text-indigo-600 hover:text-indigo-800 font-semibold underline"
              >
                我已登录
              </button>
            </div>
          )}

          {step === 'success' && (
            <div className="py-6 space-y-4">
              <div className="w-16 h-16 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center mx-auto shadow-xs anim-modal-enter">
                <CheckCircle2 className="w-9 h-9" />
              </div>
              <div>
                <h4 className="text-lg font-bold text-slate-900">登录成功！</h4>
                <p className="text-xs text-slate-500 mt-1">
                  已成功提取当前会话 Cookies 并写入本地数据库备用。
                </p>
              </div>

              <div className="bg-emerald-50 text-emerald-800 p-3 rounded-2xl border border-emerald-200/60 text-xs text-left space-y-1">
                <div className="flex items-center gap-1.5 font-bold">
                  <ShieldCheck className="w-4 h-4 text-emerald-600" /> 登录态续期完毕
                </div>
                <div className="text-[11px] text-emerald-700">
                  账号状态已更新为「已启用」，可以正常进行全量或增量抓取。
                </div>
              </div>

              <button
                type="button"
                onClick={onClose}
                className="w-full py-2.5 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-xl shadow-xs"
              >
                完成并返回
              </button>
            </div>
          )}

          {step === 'expired' && (
            <div className="py-6 space-y-3">
              <AlertTriangle className="w-10 h-10 text-amber-500 mx-auto" />
              <h4 className="text-base font-bold text-slate-900">登录未完成</h4>
              <p className="text-xs text-slate-500">{errorMsg || '超时未检测到扫码，请重试'}</p>
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 bg-slate-900 text-white text-xs font-bold rounded-xl shadow-xs inline-flex items-center gap-1.5"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                关闭后重新发起登录
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
