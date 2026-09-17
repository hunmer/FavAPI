import React, { useMemo, useState } from 'react';
import { Account, FetchTargetSpec, ScrapeRequest } from '../../../types';
import { uploadWechatJson } from '../../../api';
import { Bookmark, Clock, Heart, ListVideo, Play, RefreshCw, Upload, X } from 'lucide-react';

interface ScrapeFormProps {
  account: Account;
  /** 可抓取入库的列表目标（收藏/喜欢/稍后再看…），由后端 /platforms 元数据驱动 */
  fetchTargets: FetchTargetSpec[];
  /** FolderPicker 选中的收藏夹（Bilibili media_id），打开表单时预填 */
  folderMediaId: string;
  isScrapingInProgress: boolean;
  onTriggerScrape: (req: ScrapeRequest) => void;
}

/** 抓取目标卡片图标：按 action 约定映射，未识别回落列表图标 */
const targetIcon = (action: string) => {
  if (action.includes('like')) return Heart;
  if (action.includes('watchlater')) return Clock;
  if (action.includes('favorite') || action.includes('collect')) return Bookmark;
  return ListVideo;
};

// 表单持久化：按「账号 + 目标」隔离存 localStorage，提交时写入、打开时回填
const formStorageKey = (accountId: string, action: string) => `favapi:scrape-form:${accountId}:${action}`;

const loadStoredForm = (accountId: string, target: FetchTargetSpec): Record<string, string> => {
  const defaults = Object.fromEntries(target.params.map((p) => [p.key, p.options?.[0]?.value ?? '']));
  try {
    const raw = localStorage.getItem(formStorageKey(accountId, target.action));
    if (!raw) return defaults;
    const saved = JSON.parse(raw) as Record<string, unknown>;
    // 仅回填该目标当前仍定义的参数 key，目标定义变更后旧值自动失效回落默认
    const restored = { ...defaults };
    for (const p of target.params) {
      if (typeof saved?.[p.key] === 'string') restored[p.key] = saved[p.key] as string;
    }
    return restored;
  } catch {
    return defaults;
  }
};

/** 抓取入口：目标卡片网格，点击弹出参数表单，提交后经 /fetch 管线入库（结果带来源标记）。 */
export const ScrapeForm: React.FC<ScrapeFormProps> = ({
  account,
  fetchTargets,
  folderMediaId,
  isScrapingInProgress,
  onTriggerScrape,
}) => {
  const [activeTarget, setActiveTarget] = useState<FetchTargetSpec | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});
  const [isAsync, setIsAsync] = useState(false);

  const openTargetModal = (target: FetchTargetSpec) => {
    setActiveTarget(target);
    const restored = loadStoredForm(account.id, target);
    // FolderPicker 联动：media_id 参数为空时带入当前选中的收藏夹
    if (folderMediaId && target.params.some((p) => p.key === 'media_id') && !restored.media_id) {
      restored.media_id = folderMediaId;
    }
    setForm(restored);
    setIsAsync(false);
  };

  const requiredMissing = useMemo(
    () =>
      !!activeTarget &&
      activeTarget.params.some((p) => p.required && p.type !== 'file' && !(form[p.key] || '').trim()),
    [activeTarget, form]
  );

  const submit = () => {
    if (!activeTarget || requiredMissing) return;
    // 去掉空值参数，让后端走默认逻辑
    const params: Record<string, any> = {};
    for (const [key, value] of Object.entries(form)) {
      const v = String(value ?? '').trim();
      if (v !== '') params[key] = v;
    }
    try {
      localStorage.setItem(formStorageKey(account.id, activeTarget.action), JSON.stringify(form));
    } catch {
      /* 存储失败（隐私模式/配额）不影响执行 */
    }
    onTriggerScrape({ action: activeTarget.action, params, isAsync });
    setActiveTarget(null);
  };

  const handleWechatUpload = async (file: File) => {
    try {
      const result = await uploadWechatJson(account.id, file);
      setForm((f) => ({ ...f, json_path: result.json_path }));
    } catch {
      /* 上传错误由抓取校验提示 */
    }
  };

  return (
    <div className="space-y-4">
      {/* 抓取目标卡片网格 */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-2.5">
        {fetchTargets.map((target) => {
          const Icon = targetIcon(target.action);
          return (
            <button
              key={target.action}
              type="button"
              disabled={isScrapingInProgress}
              onClick={() => openTargetModal(target)}
              className="p-3.5 rounded-xl border border-slate-200 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-800 text-left transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-xs font-bold text-slate-900 dark:text-white flex items-center gap-1.5">
                  <Icon className="w-3.5 h-3.5 text-indigo-500" />
                  {target.name}
                </span>
                {target.source && (
                  <span className="text-[9px] bg-indigo-50 dark:bg-indigo-950 text-indigo-600 dark:text-indigo-400 px-1.5 py-0.5 rounded font-semibold shrink-0">
                    {target.source}
                  </span>
                )}
              </div>
              <div className="text-[11px] text-slate-500 dark:text-slate-400 leading-snug line-clamp-2">
                {target.description}
              </div>
            </button>
          );
        })}
      </div>

      {/* 状态提示行 */}
      <div className="text-xs text-slate-500 dark:text-slate-400">
        {isScrapingInProgress ? (
          <span className="inline-flex items-center gap-1.5 text-indigo-600 font-semibold animate-pulse">
            <RefreshCw className="w-3.5 h-3.5 animate-spin" />
            正在实时采集数据并解析媒体元信息...
          </span>
        ) : (
          <span>点击卡片配置参数后开始抓取，结果实时入库并在下方滚动展示</span>
        )}
      </div>

      {/* 抓取参数弹窗（表单定义来自后端 fetch_targets 元数据） */}
      {activeTarget && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="relative anim-modal-enter bg-white dark:bg-[#161B26] w-full max-w-lg rounded-[28px] p-6 shadow-2xl border border-slate-100 dark:border-slate-800 max-h-[85vh] flex flex-col overflow-hidden">
            <button
              type="button"
              onClick={() => setActiveTarget(null)}
              className="absolute top-4 right-4 z-10 p-1.5 rounded-xl text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            >
              <X className="w-4 h-4" />
            </button>

            <div className="space-y-4 overflow-y-auto pr-1">
              <div>
                <h3 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
                  {activeTarget.name}
                  {activeTarget.source && (
                    <span className="text-[10px] bg-indigo-50 dark:bg-indigo-950 text-indigo-600 dark:text-indigo-400 px-2 py-0.5 rounded-full font-semibold">
                      入库来源：{activeTarget.source}
                    </span>
                  )}
                </h3>
                {activeTarget.description && (
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">{activeTarget.description}</p>
                )}
              </div>

              {activeTarget.params.map((p) => (
                <div key={p.key}>
                  <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5">
                    {p.label}
                    {p.required && <span className="text-rose-500 ml-0.5">*</span>}
                  </label>
                  {p.type === 'select' && p.options && p.options.length > 0 ? (
                    <select
                      value={form[p.key] || p.options[0].value}
                      onChange={(e) => setForm((f) => ({ ...f, [p.key]: e.target.value }))}
                      className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 text-sm bg-white dark:bg-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-slate-900"
                    >
                      {p.options.map((o) => (
                        <option key={o.value} value={o.value}>{o.label}</option>
                      ))}
                    </select>
                  ) : p.type === 'textarea' ? (
                    <textarea
                      value={form[p.key] || ''}
                      onChange={(e) => setForm((f) => ({ ...f, [p.key]: e.target.value }))}
                      placeholder={p.placeholder}
                      rows={4}
                      className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 text-xs font-mono bg-transparent dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-slate-900"
                    />
                  ) : (
                    <input
                      type={p.type === 'number' ? 'number' : p.type === 'date' ? 'date' : 'text'}
                      value={form[p.key] || ''}
                      onChange={(e) => setForm((f) => ({ ...f, [p.key]: e.target.value }))}
                      placeholder={p.placeholder}
                      className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 text-sm bg-transparent dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-slate-900"
                    />
                  )}
                  {p.help && <p className="text-[11px] text-slate-400 mt-1">{p.help}</p>}

                  {/* 微信收藏 JSON：参数旁附带文件上传（路径自动回填） */}
                  {p.key === 'json_path' && (
                    <label className="mt-2 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 text-white text-xs font-semibold cursor-pointer hover:bg-emerald-700 transition-colors">
                      <Upload className="w-3.5 h-3.5" />
                      上传 JSON 文件
                      <input
                        type="file"
                        accept=".json,application/json"
                        className="hidden"
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          if (file) void handleWechatUpload(file);
                        }}
                      />
                    </label>
                  )}
                </div>
              ))}

              {/* 执行模式：同步流式 / 后台异步 */}
              <div className="flex items-center justify-between p-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-800/60">
                <span className="text-xs font-medium text-slate-700 dark:text-slate-200">
                  {isAsync ? '后台异步任务 (不阻塞界面)' : '同步流式返回 (实时查看)'}
                </span>
                <button
                  type="button"
                  onClick={() => setIsAsync(!isAsync)}
                  className={`w-10 h-5 rounded-full transition-colors relative ${
                    isAsync ? 'bg-slate-900 dark:bg-slate-600' : 'bg-slate-300 dark:bg-slate-600'
                  }`}
                >
                  <span
                    className={`absolute top-0.5 left-0.5 bg-white w-4 h-4 rounded-full transition-transform ${
                      isAsync ? 'translate-x-5' : ''
                    }`}
                  />
                </button>
              </div>
              <p className="text-[11px] text-slate-400 -mt-2">推荐大量抓取时使用异步模式。</p>

              <div className="flex justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => setActiveTarget(null)}
                  className="px-4 py-2 text-xs font-semibold text-slate-600 dark:text-slate-300 hover:text-slate-800 dark:hover:text-slate-100 rounded-xl"
                >
                  取消
                </button>
                <button
                  type="button"
                  disabled={requiredMissing}
                  onClick={submit}
                  className="px-5 py-2 text-xs font-bold text-white rounded-xl shadow-xs disabled:opacity-50 bg-slate-900 hover:bg-slate-800 dark:bg-slate-700 dark:hover:bg-slate-600 inline-flex items-center gap-1.5"
                >
                  <Play className="w-3.5 h-3.5 fill-current" />
                  开始抓取
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
