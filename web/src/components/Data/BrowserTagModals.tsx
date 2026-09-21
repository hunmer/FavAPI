import React, { useRef, useState } from 'react';
import { AlertTriangle, Trash2, X, Plus, Sparkles, Loader2, Wand2, FolderPlus, RefreshCw } from 'lucide-react';
import { useDismiss } from '../../hooks/useDismiss';
import * as api from '../../api';

/** 标签右键菜单（自 DataBrowserView 抽离）：点击外部/滚动自动关闭 */
export const BrowserTagContextMenu: React.FC<{
  ctxMenu: { x: number; y: number; tag: string };
  onClose: () => void;
  onDeleteTag: (tag: string) => void;
}> = ({ ctxMenu, onClose, onDeleteTag }) => {
  // 浮层内部点击由按钮 onClick 自行处理
  const tagMenuRef = useRef<HTMLDivElement>(null);
  useDismiss(onClose, true, tagMenuRef);

  return (
    <div
      ref={tagMenuRef}
      className="fixed z-[60] py-1 rounded-xl bg-white dark:bg-[#161B26] border border-slate-200 dark:border-slate-700 shadow-lg overflow-hidden anim-modal-enter"
      style={{ left: Math.min(ctxMenu.x, window.innerWidth - 140), top: ctxMenu.y }}
      onClick={(e) => e.stopPropagation()}
    >
      <button
        type="button"
        onClick={() => onDeleteTag(ctxMenu.tag)}
        className="w-full px-3.5 py-2 text-left text-xs font-semibold text-rose-600 hover:bg-rose-50 flex items-center gap-2 cursor-pointer"
      >
        <Trash2 className="w-3.5 h-3.5" />
        删除标签「{ctxMenu.tag}」
      </button>
    </div>
  );
};

/** 删除标签确认（AlertDialog + checkbox，默认不勾选） */
export const BrowserTagDeleteModal: React.FC<{
  confirm: { tag: string; usage: number };
  alsoContents: boolean;
  onAlsoContentsChange: (v: boolean) => void;
  deleting: boolean;
  onClose: () => void;
  onConfirm: () => void;
}> = ({ confirm, alsoContents, onAlsoContentsChange, deleting, onClose, onConfirm }) => (
  <div
    className="fixed inset-0 z-[70] bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 anim-backdrop-enter"
    onClick={() => !deleting && onClose()}
  >
    <div
      onClick={(e) => e.stopPropagation()}
      className="anim-modal-enter bg-white dark:bg-[#161B26] w-full max-w-sm rounded-[28px] p-6 shadow-2xl border border-slate-100 dark:border-slate-800 space-y-4"
    >
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-2xl bg-rose-50 dark:bg-rose-950 text-rose-600 dark:text-rose-400 flex items-center justify-center shrink-0">
          <AlertTriangle className="w-5 h-5" />
        </div>
        <h3 className="text-base font-bold text-slate-900 dark:text-white">删除标签</h3>
      </div>
      <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
        将从
        {confirm.usage >= 0 ? (
          <>
            <strong className="text-slate-900 dark:text-white">{confirm.usage}</strong> 条内容中
          </>
        ) : ''}{' '}
        移除标签 <span className="font-bold text-violet-600">#{confirm.tag}</span>
        （含各分组内的该标签）。
      </p>
      <label className="flex items-start gap-2.5 p-3 rounded-2xl bg-rose-50/60 border border-rose-100 cursor-pointer">
        <input
          type="checkbox"
          checked={alsoContents}
          onChange={(e) => onAlsoContentsChange(e.target.checked)}
          className="mt-0.5 w-4 h-4 rounded accent-rose-600 cursor-pointer"
        />
        <span className="text-xs text-slate-700 dark:text-slate-300">
          <strong className="text-rose-600 dark:text-rose-400">一并删除这些收藏内容</strong>
          <span className="block text-[11px] text-slate-400 mt-0.5">
            含该标签的收藏将全部从收藏库移除（不可恢复），内容元数据保留
          </span>
        </span>
      </label>
      <div className="flex justify-end gap-2 pt-1">
        <button
          type="button"
          onClick={onClose}
          disabled={deleting}
          className="px-4 py-2 text-xs font-semibold text-slate-600 dark:text-slate-300 hover:text-slate-800 dark:hover:text-slate-100 rounded-xl cursor-pointer"
        >
          取消
        </button>
        <button
          type="button"
          onClick={onConfirm}
          disabled={deleting}
          className="px-4 py-2 bg-rose-600 hover:bg-rose-700 disabled:opacity-50 text-white text-xs font-bold rounded-xl flex items-center gap-1.5 cursor-pointer"
        >
          <Trash2 className="w-3.5 h-3.5" />
          {deleting ? '删除中...' : alsoContents ? '删除标签与收藏' : '删除标签'}
        </button>
      </div>
    </div>
  </div>
);

/** 智能创建·继续优化对话框：展示历史优化要求 + 输入新要求（叠在新建分组弹窗之上） */
export const SuggestRefineModal: React.FC<{
  baseKeyword: string;
  history: string[];
  busy: boolean;
  error: string;
  onClose: () => void;
  onSubmit: (instruction: string) => void;
}> = ({ baseKeyword, history, busy, error, onClose, onSubmit }) => {
  const [text, setText] = useState('');
  return (
    <div
      className="fixed inset-0 z-[80] bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 anim-backdrop-enter"
      onClick={() => !busy && onClose()}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="anim-modal-enter bg-white dark:bg-[#161B26] w-full max-w-sm rounded-[28px] shadow-2xl border border-slate-100 dark:border-slate-800 overflow-hidden"
      >
        <div className="p-5 bg-slate-50 dark:bg-slate-800 border-b border-slate-100 dark:border-slate-800">
          <h3 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
            <Wand2 className="w-4 h-4 text-violet-600" />
            继续优化建议
          </h3>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            AI 会结合对话历史，基于「{baseKeyword}」的上一版建议按新要求调整
          </p>
        </div>
        <div className="p-5 space-y-4">
          {/* 历史优化要求 */}
          <div>
            <span className="text-xs font-bold text-slate-600 dark:text-slate-400 block mb-2">
              历史优化要求{history.length > 0 ? `（${history.length} 轮）` : ''}
            </span>
            {history.length === 0 ? (
              <p className="text-[11px] text-slate-400">还没有优化要求，直接在下方输入第一条。</p>
            ) : (
              <div className="flex flex-col gap-1.5 max-h-40 overflow-y-auto pr-0.5">
                {history.map((h, i) => (
                  <div key={i} className="flex items-start gap-2 px-3 py-2 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-100 dark:border-slate-700">
                    <span className="shrink-0 mt-0.5 w-4 h-4 rounded-full bg-violet-100 dark:bg-violet-950 text-violet-600 dark:text-violet-400 text-[9px] font-bold flex items-center justify-center">
                      {i + 1}
                    </span>
                    <span className="text-[11px] text-slate-600 dark:text-slate-300 leading-relaxed break-all">{h}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
          {/* 新要求 */}
          <div className="flex flex-col gap-2">
            <textarea
              autoFocus
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  if (text.trim() && !busy) onSubmit(text.trim());
                }
              }}
              rows={2}
              placeholder="新的优化要求，如：标签更偏新手向、去掉商业化分组"
              className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 text-sm dark:bg-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-violet-600 resize-none"
            />
            {error && <p className="text-[11px] text-rose-600 break-all">{error}</p>}
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={onClose}
                disabled={busy}
                className="px-4 py-2 text-xs font-semibold text-slate-600 dark:text-slate-300 hover:text-slate-800 dark:hover:text-slate-100 rounded-xl cursor-pointer"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => text.trim() && onSubmit(text.trim())}
                disabled={busy || !text.trim()}
                className="px-4 py-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white text-xs font-bold rounded-xl flex items-center gap-1.5 cursor-pointer"
              >
                {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Wand2 className="w-3.5 h-3.5" />}
                {busy ? '优化中...' : '提交优化'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

/** 新建标签分组弹窗：手动创建 / 智能创建（关键词 → AI 联想分组与标签，默认全选可切换）双 tab */
export const BrowserGroupCreateModal: React.FC<{
  groups: api.TagGroupRow[];
  name: string;
  onNameChange: (v: string) => void;
  pickedTags: string[];
  onTogglePickedTag: (t: string) => void;
  saving: boolean;
  onClose: () => void;
  onSubmit: () => void;
  /** AI Agent 配置（智能创建用，内部自动过滤出 OpenAI 兼容方式） */
  agents: api.AgentConfigRow[];
  /** 智能创建应用成功后刷新（打标池与过滤面板同步） */
  onApplied: (summary: { created: number; merged: number; added_tags: number }) => void;
}> = ({ groups, name, onNameChange, pickedTags, onTogglePickedTag, saving, onClose, onSubmit, agents, onApplied }) => {
  const [tab, setTab] = useState<'manual' | 'smart'>('manual');

  // ---------- 智能创建状态（仅弹窗内使用） ----------
  const openaiAgents = agents.filter((a) => a.provider !== 'jev');
  const [smartAgentId, setSmartAgentId] = useState(openaiAgents[0]?.agent_id || '');
  const [keyword, setKeyword] = useState('');
  const [suggesting, setSuggesting] = useState(false);
  const [applying, setApplying] = useState(false);
  const [smartError, setSmartError] = useState('');
  // AI 建议：[{name, tags}]（name 可编辑）；selected 存 `${组索引}::${标签}`（改名不失配），默认全选
  const [suggestions, setSuggestions] = useState<Array<{ name: string; tags: string[] }>>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  // 多轮优化：baseKeyword=首次联想的关键词（重新生成用）；sessionId=后端内存会话（继续优化用）
  const [baseKeyword, setBaseKeyword] = useState('');
  const [sessionId, setSessionId] = useState('');
  // 继续优化对话框：历史用户要求（前端维护，重新生成/新联想时清空）
  const [showRefine, setShowRefine] = useState(false);
  const [refineHistory, setRefineHistory] = useState<string[]>([]);
  const [refineError, setRefineError] = useState('');

  const existingNames = new Set(groups.map((g) => g.group));
  const tagKey = (groupIdx: number, tag: string) => `${groupIdx}::${tag}`;
  const hasSuggested = suggestions.length > 0;

  const applySuggestionResult = (r: { groups: Array<{ name: string; tags: string[] }>; session_id: string }) => {
    setSuggestions(r.groups);
    setSelected(new Set(r.groups.flatMap((g, gi) => g.tags.map((t) => tagKey(gi, t)))));
    setSessionId(r.session_id);
  };

  /** 联想 / 重新生成：无会话时用输入框关键词首次联想；已有建议时用输入框新词或原关键词全新生成（清空优化历史） */
  const runSuggest = async () => {
    if (!smartAgentId || suggesting) return;
    const kw = (hasSuggested ? keyword.trim() || baseKeyword : keyword.trim());
    if (!kw) return;
    setSuggesting(true);
    setSmartError('');
    try {
      applySuggestionResult(await api.suggestTagGroups(smartAgentId, kw));
      setBaseKeyword(kw);
      setRefineHistory([]);
      setRefineError('');
      setKeyword('');
    } catch (err: any) {
      setSmartError(err?.message || 'AI 生成失败');
    } finally {
      setSuggesting(false);
    }
  };

  /** 继续优化（对话框提交）：指令追加到后端会话让 AI 基于上一版建议调整，成功后计入历史 */
  const refineSuggest = async (instruction: string) => {
    if (!smartAgentId || !sessionId || suggesting) return;
    setSuggesting(true);
    setRefineError('');
    try {
      applySuggestionResult(await api.suggestTagGroups(smartAgentId, baseKeyword, { sessionId, instruction }));
      setRefineHistory((prev) => [...prev, instruction]);
      setShowRefine(false);
    } catch (err: any) {
      setRefineError(err?.message || 'AI 优化失败');
    } finally {
      setSuggesting(false);
    }
  };

  /** 编辑建议分组名；清空名称时整组取消勾选（应用时跳过） */
  const renameSuggestion = (idx: number, newName: string) => {
    setSuggestions((prev) => prev.map((g, i) => (i === idx ? { ...g, name: newName } : g)));
    if (!newName.trim()) {
      setSelected((prev) => {
        const next = new Set(prev);
        (suggestions[idx]?.tags || []).forEach((t) => next.delete(tagKey(idx, t)));
        return next;
      });
    }
  };

  // ---------- 跨分组拖拽 ----------
  const [dragging, setDragging] = useState<{ gi: number; tag: string } | null>(null);
  const [dragOverIdx, setDragOverIdx] = useState<number | null>(null);

  /** 把标签从 fromGi 组移动到 toGi 组；勾选状态随组索引同步迁移 */
  const moveTag = (fromGi: number, tag: string, toGi: number) => {
    if (fromGi === toGi) return;
    setSuggestions((prev) => {
      const next = prev.map((g) => ({ ...g, tags: [...g.tags] }));
      const fi = next[fromGi].tags.indexOf(tag);
      if (fi < 0) return prev;
      next[fromGi].tags.splice(fi, 1);
      next[toGi].tags.push(tag);
      return next;
    });
    setSelected((prev) => {
      if (!prev.has(tagKey(fromGi, tag))) return prev;
      const next = new Set(prev);
      next.delete(tagKey(fromGi, tag));
      next.add(tagKey(toGi, tag));
      return next;
    });
  };

  const toggleTagKey = (key: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const toggleGroup = (groupIdx: number, tags: string[]) => {
    const keys = tags.map((t) => tagKey(groupIdx, t));
    setSelected((prev) => {
      const allOn = keys.every((k) => prev.has(k));
      const next = new Set(prev);
      keys.forEach((k) => (allOn ? next.delete(k) : next.add(k)));
      return next;
    });
  };

  const applySuggestions = async () => {
    if (applying || selected.size === 0) return;
    setApplying(true);
    setSmartError('');
    try {
      // 勾选项按（编辑后的）分组名聚合；两个建议组改成同名时自动合并去重
      const byGroup = new Map<string, string[]>();
      suggestions.forEach((g, gi) => {
        const name = g.name.trim();
        const picked = g.tags.filter((t) => selected.has(tagKey(gi, t)));
        if (name && picked.length) {
          const cur = byGroup.get(name) || [];
          picked.forEach((t) => { if (!cur.includes(t)) cur.push(t); });
          byGroup.set(name, cur);
        }
      });
      if (byGroup.size === 0) {
        setSmartError('没有可应用的标签（分组名为空的组会被跳过）');
        return;
      }
      const summary = await api.applyTagGroups([...byGroup.entries()].map(([n, ts]) => ({ name: n, tags: ts })));
      onApplied(summary);
      onClose();
    } catch (err: any) {
      setSmartError(err?.message || '应用失败');
    } finally {
      setApplying(false);
    }
  };

  const busy = saving || suggesting || applying;

  return (
    <div
      className="fixed inset-0 z-[70] bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 anim-backdrop-enter"
      onClick={() => !busy && onClose()}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="anim-modal-enter bg-white dark:bg-[#161B26] w-full max-w-sm rounded-[28px] shadow-2xl border border-slate-100 dark:border-slate-800 overflow-hidden"
      >
        <div className="p-5 bg-slate-50 dark:bg-slate-800 border-b border-slate-100 dark:border-slate-800">
          <h3 className="text-base font-bold text-slate-900 dark:text-white">新建标签分组</h3>
          {/* Tab 切换：手动 / 智能 */}
          <div className="mt-3 flex items-center gap-1 p-1 bg-slate-100 dark:bg-slate-900/60 rounded-2xl border border-slate-200/80 dark:border-slate-700 w-fit">
            <button
              type="button"
              onClick={() => setTab('manual')}
              className={`px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all cursor-pointer flex items-center gap-1.5 ${
                tab === 'manual'
                  ? 'bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-xs'
                  : 'text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
              }`}
            >
              <Plus className="w-3.5 h-3.5" />
              手动创建
            </button>
            <button
              type="button"
              onClick={() => setTab('smart')}
              className={`px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all cursor-pointer flex items-center gap-1.5 ${
                tab === 'smart'
                  ? 'bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-xs'
                  : 'text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
              }`}
            >
              <Sparkles className="w-3.5 h-3.5 text-violet-500" />
              智能创建
            </button>
          </div>
        </div>

        {tab === 'manual' ? (
          /* ---------- 手动创建：原有表单 ---------- */
          <div className="p-5 space-y-4">
            <input
              autoFocus
              type="text"
              value={name}
              onChange={(e) => onNameChange(e.target.value)}
              placeholder="分组名称，如：兴趣爱好"
              className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 text-sm dark:bg-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-violet-600"
            />
            {(() => {
              const otherGroup = groups.find((g) => g.group === '其他');
              const otherTags = otherGroup?.tags || [];
              if (otherTags.length === 0) {
                return (
                  <p className="text-[11px] text-slate-400">
                    当前没有未分组标签；创建空分组后，手动打标或模型新增的标签如需归组可编辑分组。
                  </p>
                );
              }
              return (
                <div>
                  <span className="text-xs font-bold text-slate-600 dark:text-slate-400 block mb-2">
                    归入「其他」组的标签（可选）
                  </span>
                  <div className="flex flex-wrap gap-1.5 max-h-40 overflow-y-auto p-1">
                    {otherTags.map((t) => {
                      const on = pickedTags.includes(t);
                      return (
                        <button
                          key={t}
                          type="button"
                          onClick={() => onTogglePickedTag(t)}
                          className={`px-2 py-1 rounded-lg text-[11px] font-medium border transition-all cursor-pointer active:scale-95 ${
                            on
                              ? 'bg-violet-600 text-white border-violet-600'
                              : 'bg-violet-50/60 dark:bg-violet-950 text-violet-600 dark:text-violet-400 border-violet-100 dark:border-violet-900 hover:bg-violet-100 dark:hover:bg-violet-900'
                          }`}
                        >
                          #{t}
                        </button>
                      );
                    })}
                  </div>
                </div>
              );
            })()}
            <div className="flex justify-end gap-2 pt-1">
              <button
                type="button"
                onClick={onClose}
                disabled={saving}
                className="px-4 py-2 text-xs font-semibold text-slate-600 dark:text-slate-300 hover:text-slate-800 dark:hover:text-slate-100 rounded-xl cursor-pointer"
              >
                取消
              </button>
              <button
                type="button"
                onClick={onSubmit}
                disabled={saving || !name.trim()}
                className="px-4 py-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white text-xs font-bold rounded-xl flex items-center gap-1.5 cursor-pointer"
              >
                <Plus className="w-3.5 h-3.5" />
                {saving ? '创建中...' : '创建分组'}
              </button>
            </div>
          </div>
        ) : (
          /* ---------- 智能创建：关键词 → AI 联想 → 勾选应用 ---------- */
          <div className="p-5 space-y-4">
            {openaiAgents.length === 0 ? (
              <p className="text-xs text-slate-400 py-4 text-center">
                暂无 OpenAI 兼容方式的 Agent；请先在「设置 → AI Agent 智能打标配置」中创建
                （Jev 判定式模型只能从候选中选择，不能生成新标签）。
              </p>
            ) : (
              <>
                <div className="flex flex-col gap-2">
                  <select
                    value={smartAgentId}
                    onChange={(e) => setSmartAgentId(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-xs bg-white dark:bg-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-violet-600 cursor-pointer"
                  >
                    {openaiAgents.map((a) => (
                      <option key={a.agent_id} value={a.agent_id}>
                        {a.name}（{a.model_id}）
                      </option>
                    ))}
                  </select>
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={keyword}
                      onChange={(e) => setKeyword(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && runSuggest()}
                      placeholder={hasSuggested
                        ? `关键词（默认「${baseKeyword}」，可修改后重新生成）`
                        : '关键词，如：咖啡 / 摄影后期 / 独立游戏'}
                      className="flex-1 min-w-0 px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 text-sm dark:bg-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-violet-600"
                    />
                    {hasSuggested ? (
                      <>
                        <button
                          type="button"
                          onClick={runSuggest}
                          disabled={suggesting}
                          title="丢弃优化上下文，用当前关键词重新联想"
                          className="px-3.5 py-2.5 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 text-xs font-bold rounded-xl flex items-center gap-1.5 shrink-0 cursor-pointer disabled:opacity-50"
                        >
                          <RefreshCw className={`w-3.5 h-3.5 ${suggesting ? 'animate-spin' : ''}`} />
                          重新生成
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setRefineError('');
                            setShowRefine(true);
                          }}
                          disabled={suggesting}
                          title="在对话框中查看历史要求并输入新的优化要求"
                          className="px-3.5 py-2.5 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white text-xs font-bold rounded-xl flex items-center gap-1.5 shrink-0 cursor-pointer"
                        >
                          <Wand2 className="w-3.5 h-3.5" />
                          继续优化{refineHistory.length > 0 ? `（${refineHistory.length}）` : ''}
                        </button>
                      </>
                    ) : (
                      <button
                        type="button"
                        onClick={runSuggest}
                        disabled={suggesting || !keyword.trim()}
                        className="px-4 py-2.5 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white text-xs font-bold rounded-xl flex items-center gap-1.5 shrink-0 cursor-pointer"
                      >
                        {suggesting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Wand2 className="w-3.5 h-3.5" />}
                        {suggesting ? '生成中...' : '联想'}
                      </button>
                    )}
                  </div>
                  <p className="text-[11px] text-slate-400">
                    {hasSuggested
                      ? '「继续优化」在对话框中追加要求，AI 结合历史迭代建议；「重新生成」丢弃上下文重来。'
                      : 'AI 按关键词联想相关分组与标签（避开现有体系），生成后默认全选，点击可切换。'}
                  </p>
                </div>

                {smartError && (
                  <p className="text-[11px] text-rose-600 break-all">{smartError}</p>
                )}

                {suggestions.length > 0 && (
                  <div className="flex flex-col gap-3 max-h-64 overflow-y-auto pr-0.5">
                    <span className="text-[11px] text-slate-400">点击分组名可编辑；标签可拖拽到其他分组；改成现有分组名即为并入</span>
                    {suggestions.map((g, gi) => {
                      const name = g.name.trim();
                      const exists = existingNames.has(name);
                      const keys = g.tags.map((t) => tagKey(gi, t));
                      const groupOn = keys.length > 0 && keys.every((k) => selected.has(k));
                      const unnamed = !name;
                      const isDropTarget = dragging !== null && dragOverIdx === gi && dragging.gi !== gi && !unnamed;
                      return (
                        <div key={gi}>
                          <div className="flex items-center gap-1.5 py-0.5">
                            <FolderPlus className={`w-3 h-3 shrink-0 ${unnamed ? 'text-slate-300' : 'text-violet-400'}`} />
                            <input
                              type="text"
                              value={g.name}
                              onChange={(e) => renameSuggestion(gi, e.target.value)}
                              placeholder="分组名（空则跳过该组）"
                              className="flex-1 min-w-0 px-1.5 py-0.5 rounded-md bg-transparent border border-transparent hover:border-slate-200 dark:hover:border-slate-700 focus:border-violet-400 focus:ring-1 focus:ring-violet-500 text-[11px] font-bold text-slate-700 dark:text-slate-200 focus:outline-none"
                            />
                            {unnamed ? (
                              <span className="px-1.5 rounded-full bg-slate-50 dark:bg-slate-800 text-slate-400 text-[9px] font-semibold border border-slate-100 dark:border-slate-700 shrink-0">
                                将跳过
                              </span>
                            ) : exists ? (
                              <span
                                className="px-1.5 rounded-full bg-sky-50 dark:bg-sky-950/60 text-sky-600 dark:text-sky-400 text-[9px] font-semibold border border-sky-100 dark:border-sky-900 shrink-0"
                                title="该分组已存在，勾选标签将并入"
                              >
                                并入现有分组
                              </span>
                            ) : (
                              <span className="px-1.5 rounded-full bg-emerald-50 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 text-[9px] font-semibold border border-emerald-100 dark:border-emerald-900 shrink-0">
                                新建分组
                              </span>
                            )}
                            {!unnamed && (
                              <button
                                type="button"
                                onClick={() => toggleGroup(gi, g.tags)}
                                className="text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 text-[10px] shrink-0 cursor-pointer"
                                title={groupOn ? '整组取消' : '整组全选'}
                              >
                                {groupOn ? '取消整组' : '全选整组'}
                              </button>
                            )}
                          </div>
                          <div
                            onDragOver={(e) => {
                              if (dragging && dragging.gi !== gi && !unnamed) {
                                e.preventDefault();
                                setDragOverIdx(gi);
                              }
                            }}
                            onDragLeave={() => setDragOverIdx((v) => (v === gi ? null : v))}
                            onDrop={(e) => {
                              e.preventDefault();
                              if (dragging && !unnamed) moveTag(dragging.gi, dragging.tag, gi);
                              setDragging(null);
                              setDragOverIdx(null);
                            }}
                            className={`flex flex-wrap gap-1.5 mt-1.5 p-1.5 -m-1.5 rounded-xl transition-all ${
                              isDropTarget ? 'bg-violet-50 dark:bg-violet-950/40 ring-2 ring-violet-300 dark:ring-violet-700' : ''
                            }`}
                          >
                            {g.tags.map((t) => {
                              const on = selected.has(tagKey(gi, t));
                              const isDragging = dragging?.gi === gi && dragging?.tag === t;
                              return (
                                <button
                                  key={t}
                                  type="button"
                                  draggable={!unnamed}
                                  onDragStart={(e) => {
                                    if (unnamed) return;
                                    setDragging({ gi, tag: t });
                                    e.dataTransfer.effectAllowed = 'move';
                                  }}
                                  onDragEnd={() => {
                                    setDragging(null);
                                    setDragOverIdx(null);
                                  }}
                                  onClick={() => !unnamed && toggleTagKey(tagKey(gi, t))}
                                  disabled={unnamed}
                                  title={unnamed ? undefined : '点击勾选 · 拖拽到其他分组'}
                                  className={`px-2 py-1 rounded-lg text-[11px] font-medium border transition-all cursor-pointer active:scale-95 disabled:cursor-not-allowed ${
                                    isDragging ? 'opacity-40' : ''
                                  } ${
                                    on && !unnamed
                                      ? 'bg-violet-600 text-white border-violet-600'
                                      : 'bg-slate-50 dark:bg-slate-800 text-slate-400 dark:text-slate-500 border-slate-100 dark:border-slate-700 hover:border-slate-300 disabled:opacity-50'
                                  }`}
                                >
                                  #{t}
                                </button>
                              );
                            })}
                            {g.tags.length === 0 && (
                              <span className="text-[10px] text-slate-300 dark:text-slate-600 px-1 py-1">
                                （空分组：拖入标签或应用时跳过）
                              </span>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}

                {suggestions.length > 0 && (
                  <div className="flex items-center justify-between gap-2 pt-1">
                    <span className="text-[11px] text-slate-400">已选 {selected.size} 个标签</span>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={onClose}
                        disabled={applying}
                        className="px-4 py-2 text-xs font-semibold text-slate-600 dark:text-slate-300 hover:text-slate-800 dark:hover:text-slate-100 rounded-xl cursor-pointer"
                      >
                        取消
                      </button>
                      <button
                        type="button"
                        onClick={applySuggestions}
                        disabled={applying || selected.size === 0}
                        className="px-4 py-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white text-xs font-bold rounded-xl flex items-center gap-1.5 cursor-pointer"
                      >
                        {applying ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
                        {applying ? '添加中...' : '一键添加到标签体系'}
                      </button>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* 继续优化对话框（叠加在当前弹窗之上） */}
        {showRefine && (
          <SuggestRefineModal
            baseKeyword={baseKeyword}
            history={refineHistory}
            busy={suggesting}
            error={refineError}
            onClose={() => !suggesting && setShowRefine(false)}
            onSubmit={refineSuggest}
          />
        )}
      </div>
    </div>
  );
};
