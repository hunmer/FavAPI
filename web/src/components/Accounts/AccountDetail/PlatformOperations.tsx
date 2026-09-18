import React, { useState, useEffect, useRef } from 'react';
import { Account } from '../../../types';
import { executeOperationStream, listPlatforms, OperationStreamEvent, OperationSpec } from '../../../api';
import { AlertTriangle, Terminal, X, Zap } from 'lucide-react';

interface PlatformOperationsProps {
  account: Account;
}

// 操作表单持久化：按「账号 + 操作」隔离存 localStorage，提交时写入、打开时回填
const opFormStorageKey = (accountId: string, opId: string) => `favapi:op-form:${accountId}:${opId}`;

const loadStoredOpForm = (accountId: string, op: OperationSpec): Record<string, string> => {
  const defaults = Object.fromEntries(op.params.map((p) => [p.key, p.options?.[0]?.value ?? '']));
  try {
    const raw = localStorage.getItem(opFormStorageKey(accountId, op.op_id));
    if (!raw) return defaults;
    const saved = JSON.parse(raw) as Record<string, unknown>;
    // 仅回填该操作当前仍定义的参数 key，操作定义变更后旧值自动失效回落默认
    const restored = { ...defaults };
    for (const p of op.params) {
      if (typeof saved?.[p.key] === 'string') restored[p.key] = saved[p.key] as string;
    }
    return restored;
  } catch {
    return defaults;
  }
};

/** 平台 API 操作：功能卡片 + 弹窗表单执行（SSE 流式），操作列表来自 GET /platforms */
export const PlatformOperations: React.FC<PlatformOperationsProps> = ({ account }) => {
  const [operations, setOperations] = useState<OperationSpec[]>([]);
  const [activeOp, setActiveOp] = useState<OperationSpec | null>(null);
  const [opForm, setOpForm] = useState<Record<string, string>>({});
  const [opRunning, setOpRunning] = useState(false);
  const [opEvents, setOpEvents] = useState<OperationStreamEvent[]>([]);
  const [showOpDangerConfirm, setShowOpDangerConfirm] = useState(false);
  const opAbortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    setOperations([]);
    listPlatforms()
      .then((rows) => {
        const row = rows.find((r) => r.platform === account.platform);
        setOperations(row?.api_operations || []);
      })
      .catch(() => {/* 拉取失败静默：不显示卡片区 */});
  }, [account.platform]);

  const openOperationModal = (op: OperationSpec) => {
    console.debug('[AccountDetail][operation] open modal', {
      accountId: account.id,
      platform: account.platform,
      opId: op.op_id,
      params: op.params.map((p) => p.key),
    });
    setActiveOp(op);
    setOpForm(loadStoredOpForm(account.id, op));
    setOpEvents([]);
    setShowOpDangerConfirm(false);
  };

  const describeOpEvent = (ev: OperationStreamEvent): string => {
    switch (ev.type) {
      case 'stage':
        return `拉取列表：第 ${ev.page} 页（本页 ${ev.total_fetched} 条）`;
      case 'progress': {
        // 日期区间管道式取消：带日期位置与累计取消数；ID 列表模式：分批进度
        if (ev.matched_this_page !== undefined) {
          const oldest = ev.oldest_collected_at?.slice(0, 10) || '游标未知';
          const fetched = ev.fetched_this_page !== undefined ? ` · 抓取 ${ev.fetched_this_page} 条` : '';
          // 命中的翻页行不需要累计取消；未命中的行用于呈现扫描后分批取消进度
          if (ev.matched_this_page > 0) {
            return `第 ${ev.page} 页 · 已翻至 ${oldest}${fetched} · 本页命中 ${ev.matched_this_page} 条`;
          }
          return `第 ${ev.page} 页 · 已翻至 ${oldest}${fetched} · 本页命中 0 条 · 累计取消 ${ev.canceled} 条`;
        }
        return `分批进度：第 ${ev.batch_no}/${ev.total_batches} 批完成（累计 ${ev.done} 条）`;
      }
      case 'done': {
        const r = ev.result || {};
        // 取消类操作带 canceled；纯拉取类按 total/matched 汇报
        if (r.canceled !== undefined) {
          const pages = r.pages ? `，翻 ${r.pages} 页` : r.batches ? `，共 ${r.batches} 批` : '';
          return `完成：匹配 ${r.matched ?? '-'} 条，已取消 ${r.canceled ?? '-'} 条${pages}`;
        }
        const matched = r.matched !== undefined ? `，命中 ${r.matched} 条` : '';
        return `完成：获取 ${r.total ?? '-'} 条${matched}${r.has_more ? '（还有更多未拉取）' : ''}`;
      }
      case 'canceled':
        return '⊘ 已手动取消，后台执行已中止';
      default:
        return '';
    }
  };

  const submitOperation = async () => {
    if (!activeOp) {
      console.warn('[AccountDetail][operation] submit ignored: no active operation');
      return;
    }
    if (activeOp.danger && !showOpDangerConfirm) {
      console.debug('[AccountDetail][operation] danger confirmation required', {
        accountId: account.id,
        opId: activeOp.op_id,
      });
      setShowOpDangerConfirm(true);
      return;
    }
    const startedAt = performance.now();
    console.groupCollapsed('[AccountDetail][operation] submit');
    console.debug('request', {
      accountId: account.id,
      opId: activeOp.op_id,
      params: opForm,
      endpoint: `/api/v1/accounts/${account.id}/operations/${activeOp.op_id}/stream`,
    });
    setOpRunning(true);
    setOpEvents([]);
    try {
      localStorage.setItem(opFormStorageKey(account.id, activeOp.op_id), JSON.stringify(opForm));
    } catch {
      /* 存储失败（隐私模式/配额）不影响执行 */
    }
    const controller = new AbortController();
    opAbortRef.current = controller;
    try {
      const done = await executeOperationStream(
        account.id,
        activeOp.op_id,
        opForm,
        (ev) => {
          console.debug('[AccountDetail][operation] stream event', ev);
          setOpEvents((prev) => [...prev, ev]);
        },
        controller.signal
      );
      console.debug('[AccountDetail][operation] completed', {
        elapsedMs: Math.round(performance.now() - startedAt),
        done,
      });
    } catch (e) {
      if (controller.signal.aborted) {
        console.debug('[AccountDetail][operation] canceled by user', {
          elapsedMs: Math.round(performance.now() - startedAt),
        });
        setOpEvents((prev) => [...prev, { type: 'canceled' }]);
      } else {
        console.error('[AccountDetail][operation] failed', {
          elapsedMs: Math.round(performance.now() - startedAt),
          error: e,
        });
        setOpEvents((prev) => [...prev, { type: 'error', message: e instanceof Error ? e.message : String(e) }]);
      }
    } finally {
      console.debug('[AccountDetail][operation] finished', {
        elapsedMs: Math.round(performance.now() - startedAt),
      });
      console.groupEnd();
      setOpRunning(false);
      if (opAbortRef.current === controller) opAbortRef.current = null;
    }
  };

  const cancelOperation = () => {
    console.debug('[AccountDetail][operation] cancel requested', {
      accountId: account.id,
      opId: activeOp?.op_id,
    });
    opAbortRef.current?.abort();
  };

  if (operations.length === 0) return null;

  return (
    <>
      {/* Platform API Operations cards */}
      <div className="bg-white dark:bg-[#161B26] p-4 sm:p-5 rounded-2xl border border-slate-200/80 dark:border-slate-800 shadow-2xs">
        <div className="flex items-center justify-between mb-3">
          <h4 className="text-xs font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
            <Zap className="w-4 h-4 text-amber-500" />
            平台 API 操作
          </h4>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
          {operations.map((op) => (
            <button
              key={op.op_id}
              type="button"
              onClick={() => openOperationModal(op)}
              className={`p-3 rounded-xl border text-left transition-all ${
                op.danger
                  ? 'border-rose-200 dark:border-rose-900 hover:border-rose-300 dark:hover:border-rose-800 hover:bg-rose-50/50 dark:hover:bg-rose-950/40'
                  : 'border-slate-200 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-800'
              }`}
            >
              <div className="flex items-center justify-between text-xs font-bold mb-1">
                <span className={op.danger ? 'text-rose-700 dark:text-rose-400' : 'text-slate-900 dark:text-white'}>{op.name}</span>
                {op.danger && (
                  <span className="text-[9px] bg-rose-100 dark:bg-rose-950 text-rose-600 dark:text-rose-400 px-1.5 py-0.5 rounded font-semibold">
                    危险操作
                  </span>
                )}
              </div>
              <div className="text-[11px] text-slate-500 dark:text-slate-400 leading-snug line-clamp-2">
                {op.description}
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* API Operation Execute Modal（左：表单 / 右：执行结果） */}
      {activeOp && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="relative anim-modal-enter bg-white dark:bg-[#161B26] w-full max-w-3xl rounded-[28px] p-6 shadow-2xl border border-slate-100 dark:border-slate-800 max-h-[85vh] flex flex-col overflow-hidden">
            <button
              type="button"
              disabled={opRunning}
              onClick={() => setActiveOp(null)}
              className="absolute top-4 right-4 z-10 p-1.5 rounded-xl text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors disabled:opacity-50"
            >
              <X className="w-4 h-4" />
            </button>
            <div className="grid grid-cols-1 md:grid-cols-2 grid-rows-2 md:grid-rows-1 gap-6 flex-1 min-h-0">
              {/* 左栏：参数表单（内容超高时内部滚动） */}
              <div className="space-y-4 min-h-0 overflow-y-auto">
                <div>
                  <h3 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
                    {activeOp.name}
                    {activeOp.danger && (
                      <span className="text-[10px] bg-rose-100 dark:bg-rose-950 text-rose-600 dark:text-rose-400 px-2 py-0.5 rounded-full font-semibold">
                        危险操作
                      </span>
                    )}
                  </h3>
                  {activeOp.description && (
                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">{activeOp.description}</p>
                  )}
                </div>

                {activeOp.params.map((p) => (
                  <div key={p.key}>
                    <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5">
                      {p.label}
                      {p.required && <span className="text-rose-500 ml-0.5">*</span>}
                    </label>
                    {p.type === 'select' && p.options && p.options.length > 0 ? (
                      <select
                        value={opForm[p.key] || p.options[0].value}
                        onChange={(e) => setOpForm((f) => ({ ...f, [p.key]: e.target.value }))}
                        className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 text-sm bg-white dark:bg-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-slate-900"
                      >
                        {p.options.map((o) => (
                          <option key={o.value} value={o.value}>{o.label}</option>
                        ))}
                      </select>
                    ) : p.type === 'textarea' ? (
                      <textarea
                        value={opForm[p.key] || ''}
                        onChange={(e) => setOpForm((f) => ({ ...f, [p.key]: e.target.value }))}
                        placeholder={p.placeholder}
                        rows={5}
                        className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 text-xs font-mono bg-transparent dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-slate-900"
                      />
                    ) : (
                      <input
                        type={p.type === 'number' ? 'number' : p.type === 'date' ? 'date' : 'text'}
                        value={opForm[p.key] || ''}
                        onChange={(e) => setOpForm((f) => ({ ...f, [p.key]: e.target.value }))}
                        placeholder={p.placeholder}
                        className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 text-sm bg-transparent dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-slate-900"
                      />
                    )}
                    {p.help && <p className="text-[11px] text-slate-400 mt-1">{p.help}</p>}
                  </div>
                ))}

                {showOpDangerConfirm && (
                  <p className="text-xs text-rose-700 dark:text-rose-400 bg-rose-50 dark:bg-rose-950 border border-rose-200 dark:border-rose-800 p-3 rounded-xl flex items-start gap-2">
                    <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                    该操作不可恢复！再次点击「确认执行」将真正提交到平台。
                  </p>
                )}

                <div className="flex justify-end gap-2 pt-1">
                  <button
                    type="button"
                    disabled={opRunning}
                    onClick={() => setActiveOp(null)}
                    className="px-4 py-2 text-xs font-semibold text-slate-600 dark:text-slate-300 hover:text-slate-800 dark:hover:text-slate-100 rounded-xl disabled:opacity-50"
                  >
                    关闭
                  </button>
                  {opRunning ? (
                    <button
                      type="button"
                      onClick={cancelOperation}
                      className="px-5 py-2 text-xs font-bold text-white rounded-xl shadow-xs bg-rose-600 hover:bg-rose-700 inline-flex items-center gap-1.5"
                    >
                      <X className="w-3.5 h-3.5" />
                      取消执行
                    </button>
                  ) : (
                    <button
                      type="button"
                      disabled={activeOp.params.some((p) => p.required) && activeOp.params.some((p) => p.required && !(opForm[p.key] || '').trim())}
                      onClick={submitOperation}
                      className={`px-5 py-2 text-xs font-bold text-white rounded-xl shadow-xs disabled:opacity-50 inline-flex items-center gap-1.5 ${
                        activeOp.danger
                          ? 'bg-rose-600 hover:bg-rose-700'
                          : 'bg-slate-900 hover:bg-slate-800 dark:bg-slate-700 dark:hover:bg-slate-600'
                      }`}
                    >
                      {showOpDangerConfirm ? '确认执行' : '执行'}
                    </button>
                  )}
                </div>
              </div>

              {/* 右栏：执行结果（实时日志 + 返回 JSON），占满剩余高度，内部滚动 */}
              <div className="space-y-3 flex flex-col min-h-0 md:border-l md:border-slate-100 dark:md:border-slate-800 md:pl-6">
                <div className="text-[10px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  执行结果
                </div>

                {opRunning || opEvents.length > 0 ? (
                  <div className="flex-1 min-h-0 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-950 p-3 overflow-y-auto space-y-1">
                    <div className="text-[10px] font-mono text-slate-500 uppercase tracking-wider mb-1">
                      实时日志 {opRunning && <span className="animate-pulse">▍</span>}
                    </div>
                    {opEvents.map((ev, i) => (
                      <div
                        key={i}
                        className={`text-[11px] font-mono leading-relaxed ${
                          ev.type === 'error'
                            ? 'text-rose-400'
                            : ev.type === 'canceled'
                              ? 'text-amber-400'
                              : ev.type === 'done'
                                ? 'text-emerald-400'
                                : 'text-slate-300'
                        }`}
                      >
                        {ev.type === 'error' ? `✗ ${ev.message}` : describeOpEvent(ev)}
                        {ev.type === 'done' && ev.result !== undefined && (
                          <pre className="mt-1 whitespace-pre-wrap break-all text-slate-400">
                            {JSON.stringify(ev.result, null, 2)}
                          </pre>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="flex-1 min-h-0 rounded-xl border border-dashed border-slate-200 dark:border-slate-700 bg-slate-50/60 dark:bg-slate-800/40 flex flex-col items-center justify-center text-center gap-1.5">
                    <Terminal className="w-5 h-5 text-slate-300" />
                    <span className="text-[11px] text-slate-400">
                      填写左侧参数并点击「执行」
                      <br />
                      此处将实时显示执行进度与结果
                    </span>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
