import React from 'react';
import { Sparkles, Loader2, CheckCircle2, AlertTriangle, X } from 'lucide-react';
import { PLATFORMS } from '../../data/mockFavData';
import * as api from '../../api';

/** 一键 AI 智能打标弹窗（自 DataBrowserView 抽离）：表单 / SSE 实时进度 / 成功 / 失败四态 */
export const AiTaggingModal: React.FC<{
  agents: api.AgentConfigRow[];
  agentId: string;
  onAgentIdChange: (id: string) => void;
  platform: string;
  onPlatformChange: (p: string) => void;
  limit: number;
  onLimitChange: (n: number) => void;
  starting: boolean;
  phase: 'idle' | 'running' | 'success' | 'failed';
  result: { processed: number; tagged: number; error?: string; taskId?: string } | null;
  progress: { processed: number; tagged: number; limit: number; results: Array<{ title: string; tags: string[] }> };
  listRef: React.RefObject<HTMLDivElement | null>;
  onClose: () => void;
  onStart: () => void;
  onStop: () => void;
  onRetry: () => void;
}> = ({
  agents,
  agentId,
  onAgentIdChange,
  platform,
  onPlatformChange,
  limit,
  onLimitChange,
  starting,
  phase,
  result,
  progress,
  listRef,
  onClose,
  onStart,
  onStop,
  onRetry,
}) => {
  return (
    <div
      className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 anim-backdrop-enter"
      onClick={() => phase !== 'running' && onClose()}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="anim-modal-enter bg-white dark:bg-[#161B26] w-full max-w-md rounded-[28px] shadow-2xl border border-slate-100 dark:border-slate-800 overflow-hidden"
      >
        <div className="p-5 bg-slate-50 dark:bg-slate-800 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
          <div>
            <h3 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-violet-600" />
              一键 AI 智能打标
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              对尚未打标的收藏内容执行一次性批量打标
            </p>
          </div>
          {phase !== 'running' && (
            <button
              type="button"
              onClick={onClose}
              className="w-8 h-8 rounded-full bg-white dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600 text-slate-700 dark:text-slate-200 flex items-center justify-center shadow-2xs cursor-pointer"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>

        <div className="p-6 space-y-5">
          {phase === 'idle' ? (
            <>
              <div>
                <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5 uppercase tracking-wider">
                  AI Agent 配置 <span className="text-red-500">*</span>
                </label>
                <select
                  value={agentId}
                  onChange={(e) => onAgentIdChange(e.target.value)}
                  className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 text-sm bg-white dark:bg-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-violet-600"
                >
                  {agents.map((a) => (
                    <option key={a.agent_id} value={a.agent_id}>
                      {a.name}（{a.model_id}）
                    </option>
                  ))}
                </select>
                <p className="text-[11px] text-slate-400 mt-1">
                  可在「设置 → AI Agent 智能打标配置」中新建或测试连通性。
                </p>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5 uppercase tracking-wider">
                  打标平台
                </label>
                <select
                  value={platform}
                  onChange={(e) => onPlatformChange(e.target.value)}
                  className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 text-sm bg-white dark:bg-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-violet-600"
                >
                  <option value="">全部平台</option>
                  {PLATFORMS.filter((p) => p.isSupported).map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5 uppercase tracking-wider">
                  打标上限
                </label>
                <input
                  type="number"
                  min="1"
                  max="2000"
                  value={limit}
                  onChange={(e) => onLimitChange(Number(e.target.value))}
                  className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 text-sm dark:bg-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-violet-600"
                />
                <p className="text-[11px] text-slate-400 mt-1">
                  本次最多处理多少条未打标内容（分批请求模型，每批 20 条）。
                </p>
              </div>

              <div className="pt-1 flex items-center justify-end gap-2.5">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-4 py-2 text-xs font-semibold text-slate-600 dark:text-slate-300 hover:text-slate-800 dark:hover:text-slate-100 rounded-xl cursor-pointer"
                >
                  取消
                </button>
                <button
                  type="button"
                  onClick={onStart}
                  disabled={starting || !agentId}
                  className="px-5 py-2.5 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white text-xs font-bold rounded-xl shadow-xs flex items-center gap-1.5 cursor-pointer"
                >
                  <Sparkles className="w-4 h-4" />
                  {starting ? '提交中...' : '开始打标'}
                </button>
              </div>
            </>
          ) : phase === 'running' ? (
            <div className="flex flex-col gap-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm font-bold text-slate-900 dark:text-white">
                  <Loader2 className="w-4 h-4 text-violet-600 animate-spin" />
                  模型打标进行中...
                </div>
                <button
                  type="button"
                  onClick={onStop}
                  className="px-3 py-1.5 rounded-xl text-xs font-semibold bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-rose-50 dark:hover:bg-rose-950 hover:text-rose-600 transition-colors cursor-pointer"
                >
                  停止
                </button>
              </div>

              {/* 实时进度 */}
              <div>
                <div className="flex items-center justify-between text-xs text-slate-500 mb-1.5">
                  <span>
                    已处理 <strong className="text-slate-800 dark:text-slate-200">{progress.processed}</strong> / {progress.limit || limit} 条
                  </span>
                  <span>
                    已打标 <strong className="text-violet-600">{progress.tagged}</strong> 条
                  </span>
                </div>
                <div className="h-2 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-violet-500 rounded-full transition-all duration-500"
                    style={{ width: `${Math.min(100, (progress.processed / (progress.limit || limit)) * 100)}%` }}
                  />
                </div>
              </div>

              {/* 每批打标结果（SSE 实时追加，自动滚动到底部） */}
              <div ref={listRef} className="max-h-56 overflow-y-auto border border-slate-100 dark:border-slate-800 rounded-2xl divide-y divide-slate-50 dark:divide-slate-800 bg-slate-50/50 dark:bg-slate-800/60">
                {progress.results.length === 0 ? (
                  <div className="py-6 text-center text-xs text-slate-400">
                    等待第一批结果（每批 20 条，取决于模型响应速度）...
                  </div>
                ) : (
                  progress.results.map((r, i) => (
                    <div key={i} className="px-3.5 py-2.5 flex flex-col gap-1 anim-row-enter">
                      <div className="text-xs font-medium text-slate-800 dark:text-slate-200 line-clamp-1">{r.title}</div>
                      <div className="flex flex-wrap gap-1">
                        {r.tags.map((t) => (
                          <span key={t} className="px-1.5 py-0.5 rounded bg-violet-50 dark:bg-violet-950 text-violet-600 dark:text-violet-400 text-[10px] font-medium border border-violet-100 dark:border-violet-900">
                            #{t}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))
                )}
              </div>
              <p className="text-[11px] text-slate-400 text-right">
                任务 ID：<span className="font-mono">{result?.taskId}</span>
              </p>
            </div>
          ) : phase === 'success' ? (
            <div className="py-6 flex flex-col items-center gap-3 text-center">
              <CheckCircle2 className="w-10 h-10 text-emerald-500" />
              <div className="text-sm font-bold text-slate-900 dark:text-white">打标完成</div>
              <p className="text-xs text-slate-500">
                共处理 <strong className="text-slate-800 dark:text-slate-200">{result?.processed}</strong> 条，成功打标{' '}
                <strong className="text-slate-800 dark:text-slate-200">{result?.tagged}</strong> 条，列表与标签统计已刷新。
              </p>
              <button
                type="button"
                onClick={onClose}
                className="mt-1 px-5 py-2.5 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-xl cursor-pointer"
              >
                完成
              </button>
            </div>
          ) : (
            <div className="py-6 flex flex-col items-center gap-3 text-center">
              <AlertTriangle className="w-10 h-10 text-rose-500" />
              <div className="text-sm font-bold text-slate-900 dark:text-white">打标失败</div>
              <p className="text-xs text-rose-600 break-all">{result?.error || '未知错误'}</p>
              <button
                type="button"
                onClick={onRetry}
                className="mt-1 px-5 py-2.5 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-xl cursor-pointer"
              >
                返回重试
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
