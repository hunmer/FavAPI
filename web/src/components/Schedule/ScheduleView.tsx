import React, { useState } from 'react';
import { ScheduledSync, Account } from '../../types';
import { AgentConfigRow } from '../../api';
import { PLATFORMS } from '../../data/platforms';
import { CalendarCard } from '../Dashboard/CalendarCard';
import {
  CalendarDays,
  Clock,
  Play,
  Plus,
  CheckCircle2,
  Pause,
  AlertCircle,
  Trash2,
  X,
  Sparkles,
} from 'lucide-react';

interface ScheduleViewProps {
  schedules: ScheduledSync[];
  accounts: Account[];
  agents: AgentConfigRow[];
  onTriggerNow: (schedule: ScheduledSync) => void;
  onToggleSchedule: (scheduleId: string) => void;
  onCreateSchedule: (body: {
    action: 'list_favorites' | 'ai_tag';
    account_id: string;
    cron_expr: string;
    title: string;
    count: number;
    platform: string;
    agentId: string;
    limit: number;
  }) => Promise<void>;
  onCreateAgent: (body: { name: string; base_url: string; api_key: string; model_id: string }) => Promise<AgentConfigRow>;
  onDeleteSchedule: (scheduleId: string) => Promise<void>;
}

const CRON_PRESETS = [
  { label: '每天 18:00', value: '0 18 * * *' },
  { label: '每天 09:00 与 21:00', value: '0 9,21 * * *' },
  { label: '每 2 小时', value: '0 */2 * * *' },
  { label: '每周日 23:00', value: '0 23 * * 0' },
];

const inputCls =
  'w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900';

export const ScheduleView: React.FC<ScheduleViewProps> = ({
  schedules,
  accounts,
  agents,
  onTriggerNow,
  onToggleSchedule,
  onCreateSchedule,
  onCreateAgent,
  onDeleteSchedule,
}) => {
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<ScheduledSync | null>(null);

  // 创建表单状态
  const [formAction, setFormAction] = useState<'list_favorites' | 'ai_tag'>('list_favorites');
  const [formAccountId, setFormAccountId] = useState('');
  const [formTitle, setFormTitle] = useState('');
  const [formCron, setFormCron] = useState('0 18 * * *');
  const [formCount, setFormCount] = useState(50);
  // AI 打标表单状态
  const [formTagPlatform, setFormTagPlatform] = useState('');
  const [formAgentId, setFormAgentId] = useState('');
  const [formTagLimit, setFormTagLimit] = useState(50);
  const [showAgentForm, setShowAgentForm] = useState(false);
  const [agentForm, setAgentForm] = useState({ name: '', base_url: '', api_key: '', model_id: '' });
  const [agentSaving, setAgentSaving] = useState(false);

  const [formError, setFormError] = useState('');
  const [creating, setCreating] = useState(false);

  const supportedPlatforms = PLATFORMS.filter((p) => p.isSupported);

  const openCreate = () => {
    setFormAction('list_favorites');
    setFormAccountId(accounts[0]?.id || '');
    setFormTitle('');
    setFormCron('0 18 * * *');
    setFormCount(50);
    setFormTagPlatform('');
    setFormAgentId(agents[0]?.agent_id || '');
    setFormTagLimit(50);
    setShowAgentForm(false);
    setAgentForm({ name: '', base_url: '', api_key: '', model_id: '' });
    setFormError('');
    setShowCreateModal(true);
  };

  const submitAgent = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!agentForm.name.trim() || !agentForm.base_url.trim() || !agentForm.api_key.trim() || !agentForm.model_id.trim()) {
      setFormError('Agent 配置的名称 / Base URL / API Key / Model ID 均不能为空');
      return;
    }
    setAgentSaving(true);
    setFormError('');
    try {
      const created = await onCreateAgent({
        name: agentForm.name.trim(),
        base_url: agentForm.base_url.trim(),
        api_key: agentForm.api_key.trim(),
        model_id: agentForm.model_id.trim(),
      });
      setFormAgentId(created.agent_id);
      setShowAgentForm(false);
      setAgentForm({ name: '', base_url: '', api_key: '', model_id: '' });
    } catch (err: any) {
      setFormError(err.message || 'Agent 配置创建失败');
    } finally {
      setAgentSaving(false);
    }
  };

  const submitCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formTitle.trim()) {
      setFormError('请输入计划名称');
      return;
    }
    if (formAction === 'list_favorites' && !formAccountId) {
      setFormError('请选择绑定账号');
      return;
    }
    if (formAction === 'ai_tag' && !formAgentId) {
      setFormError('请选择 AI Agent 配置（可新建）');
      return;
    }
    setCreating(true);
    setFormError('');
    try {
      await onCreateSchedule({
        action: formAction,
        account_id: formAction === 'list_favorites' ? formAccountId : '',
        cron_expr: formCron.trim(),
        title: formTitle.trim(),
        count: formCount,
        platform: formAction === 'ai_tag' ? formTagPlatform : '',
        agentId: formAgentId,
        limit: formTagLimit,
      });
      setShowCreateModal(false);
    } catch (err: any) {
      setFormError(err.message || '创建失败');
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="p-4 sm:p-6 lg:p-8 flex flex-col lg:flex-row gap-6">
      {/* Left: Schedule List & Actions (2/3) */}
      <div className="flex-1 flex flex-col gap-6">
        {/* Header summary */}
        <div className="bg-white rounded-3xl p-6 border border-slate-100 shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
              <CalendarDays className="w-5 h-5 text-sky-600" />
              自动化定时同步任务
            </h2>
            <p className="text-xs text-slate-500 mt-1">
              通过 Cron 表达式在后台定时执行轻量增量抓取或 AI 智能打标，避免漏抓新收藏。
            </p>
          </div>

          <div className="flex items-center gap-3">
            <span className="text-xs font-semibold px-3 py-1.5 rounded-full bg-emerald-50 text-emerald-600 border border-emerald-200 flex items-center gap-1.5">
              <CheckCircle2 className="w-4 h-4" />
              {schedules.filter((s) => s.status === 'active').length} 个任务运行中
            </span>
            <button
              type="button"
              onClick={openCreate}
              className="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white rounded-2xl text-xs font-bold shadow-sm inline-flex items-center gap-1.5"
              title="新建定时计划（抓取或 AI 智能打标）"
            >
              <Plus className="w-4 h-4" />
              新建计划
            </button>
          </div>
        </div>

        {/* Schedule Cards List */}
        <div className="flex flex-col gap-3.5">
          {schedules.length === 0 && (
            <div className="bg-white rounded-3xl p-12 border border-slate-100 text-center text-xs text-slate-400">
              暂无定时计划，点击右上角「新建计划」创建第一个自动化同步任务
            </div>
          )}
          {schedules.map((item, idx) => {
            const isAiTag = item.action === 'ai_tag';
            const platform = PLATFORMS.find((p) => p.id === item.platform) || PLATFORMS[0];
            const isActive = item.status === 'active';

            return (
              <div
                key={item.id}
                className={`anim-card-enter bg-white rounded-3xl p-5 border transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-4 ${
                  isActive ? 'border-slate-100 shadow-sm' : 'border-slate-100/60 bg-slate-50/50 opacity-70'
                }`}
                style={{ animationDelay: `${Math.min(idx * 40, 240)}ms` }}
              >
                <div className="flex items-center gap-4 min-w-0">
                  <div
                    className={`w-12 h-12 rounded-2xl flex items-center justify-center shrink-0 shadow-sm ${
                      isAiTag ? 'bg-violet-50 text-violet-600' : ''
                    }`}
                    style={
                      isAiTag ? undefined : { backgroundColor: `${platform.color}15`, color: platform.color }
                    }
                  >
                    {isAiTag ? <Sparkles className="w-5 h-5" /> : <span className="font-bold text-sm">{platform.name.slice(0, 2)}</span>}
                  </div>

                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h4 className="text-sm font-bold text-slate-900">{item.title}</h4>
                      {isAiTag ? (
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded-md border bg-violet-50 text-violet-600 border-violet-200">
                          智能打标
                        </span>
                      ) : (
                        <span
                          className={`text-[10px] font-bold px-2 py-0.5 rounded-md border ${platform.badgeBg}`}
                        >
                          {platform.name.split(' ')[0]}
                        </span>
                      )}
                      {isActive ? (
                        <span className="text-[10px] font-semibold px-2 py-0.5 rounded-md bg-emerald-50 text-emerald-600 border border-emerald-200">
                          执行中
                        </span>
                      ) : (
                        <span className="text-[10px] font-semibold px-2 py-0.5 rounded-md bg-slate-100 text-slate-500">
                          已挂起
                        </span>
                      )}
                    </div>

                    <div className="flex items-center gap-3 text-xs text-slate-500 mt-1.5 flex-wrap">
                      <span className="flex items-center gap-1 font-mono bg-slate-100 px-2 py-0.5 rounded text-slate-700 font-medium">
                        <Clock className="w-3 h-3 text-slate-400" />
                        {item.cronExpr}
                      </span>
                      <span>{isAiTag ? item.accountName : `账号: ${item.accountName}`}</span>
                      <span className="text-sky-600 font-medium">下次执行: {item.nextRunTime}</span>
                    </div>
                  </div>
                </div>

                {/* Right Actions */}
                <div className="flex items-center gap-2 shrink-0 self-end sm:self-center">
                  <button
                    onClick={() => onToggleSchedule(item.id)}
                    className="px-3 py-2 rounded-xl text-xs font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200 transition-colors flex items-center gap-1.5"
                    title={isActive ? '暂停调度' : '恢复调度'}
                  >
                    {isActive ? (
                      <>
                        <Pause className="w-3.5 h-3.5 text-slate-500" />
                        暂停
                      </>
                    ) : (
                      <>
                        <Play className="w-3.5 h-3.5 text-emerald-600" />
                        启用
                      </>
                    )}
                  </button>

                  <button
                    onClick={() => onTriggerNow(item)}
                    className="px-3.5 py-2 rounded-xl text-xs font-semibold bg-slate-900 text-white hover:bg-slate-800 transition-all flex items-center gap-1.5 shadow-sm active:scale-95"
                  >
                    <Play className="w-3.5 h-3.5 fill-current" />
                    立即触发
                  </button>

                  <button
                    onClick={() => setDeleteTarget(item)}
                    className="p-2 rounded-xl text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors"
                    title="删除此计划"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Right Column: Interactive Calendar & Rules (1/3) */}
      <div className="w-full lg:w-[340px] xl:w-[380px] shrink-0 flex flex-col gap-6">
        <CalendarCard />

        <div className="bg-white rounded-3xl p-5 border border-slate-100 shadow-sm">
          <h4 className="text-sm font-bold text-slate-900 mb-2">Cron 表达式简易说明</h4>
          <div className="text-xs text-slate-500 flex flex-col gap-2 leading-relaxed">
            <div className="p-2.5 rounded-xl bg-slate-50 font-mono text-[11px] text-slate-700">
              0 18 * * * (每天下午 18:00 执行)
            </div>
            <div className="p-2.5 rounded-xl bg-slate-50 font-mono text-[11px] text-slate-700">
              0 23 * * 0 (每周日晚 23:00 全量更新)
            </div>
            <div className="p-2.5 rounded-xl bg-slate-50 font-mono text-[11px] text-slate-700">
              0 */2 * * * (每 2 小时心跳检查)
            </div>
          </div>
        </div>
      </div>

      {/* Create Schedule Modal */}
      {showCreateModal && (
        <div
          className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 anim-backdrop-enter"
          onClick={() => setShowCreateModal(false)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="anim-modal-enter bg-white w-full max-w-lg rounded-[28px] shadow-2xl border border-slate-100 overflow-hidden max-h-[92vh] flex flex-col"
          >
            <div className="p-5 sm:p-6 bg-slate-50 border-b border-slate-100 flex items-center justify-between">
              <div>
                <h3 className="text-lg font-bold text-slate-900">新建定时计划</h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  按 Cron 周期自动执行收藏增量抓取或 AI 智能打标
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowCreateModal(false)}
                className="w-8 h-8 rounded-full bg-white hover:bg-slate-200 text-slate-700 flex items-center justify-center transition-colors shadow-2xs"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={submitCreate} className="p-6 space-y-5 overflow-y-auto">
              {/* 任务类型切换 */}
              <div className="bg-slate-100 p-1 rounded-2xl border border-slate-200 flex gap-1">
                {([
                  { id: 'list_favorites', label: '收藏抓取' },
                  { id: 'ai_tag', label: 'AI 智能打标' },
                ] as const).map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => setFormAction(t.id)}
                    className={`flex-1 px-3 py-2 rounded-xl text-xs font-semibold flex items-center justify-center gap-1.5 transition-all cursor-pointer ${
                      formAction === t.id ? 'bg-white text-slate-900 shadow-xs' : 'text-slate-500 hover:text-slate-800'
                    }`}
                  >
                    {t.id === 'ai_tag' && <Sparkles className="w-3.5 h-3.5" />}
                    {t.label}
                  </button>
                ))}
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1.5 uppercase tracking-wider">
                  计划名称 <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={formTitle}
                  onChange={(e) => setFormTitle(e.target.value)}
                  placeholder={
                    formAction === 'ai_tag' ? '例如：每日 AI 收藏打标' : '例如：B站收藏夹每日增量同步'
                  }
                  className={inputCls}
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1.5 uppercase tracking-wider">
                  Cron 表达式 <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={formCron}
                  onChange={(e) => setFormCron(e.target.value)}
                  placeholder="0 18 * * *"
                  className={`${inputCls} font-mono`}
                />
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {CRON_PRESETS.map((p) => (
                    <button
                      key={p.value}
                      type="button"
                      onClick={() => setFormCron(p.value)}
                      className="px-2.5 py-1 rounded-lg bg-slate-100 hover:bg-slate-200 text-[11px] font-semibold text-slate-600 transition-colors"
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
              </div>

              {formAction === 'list_favorites' ? (
                <>
                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1.5 uppercase tracking-wider">
                      绑定账号 <span className="text-red-500">*</span>
                    </label>
                    <select
                      value={formAccountId}
                      onChange={(e) => setFormAccountId(e.target.value)}
                      className={inputCls}
                    >
                      {accounts.map((a) => (
                        <option key={a.id} value={a.id}>
                          {a.name}（{a.platform}）
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1.5 uppercase tracking-wider">
                      单次抓取数量（增量）
                    </label>
                    <input
                      type="number"
                      min="1"
                      max="1000"
                      value={formCount}
                      onChange={(e) => setFormCount(Number(e.target.value))}
                      className={inputCls}
                    />
                    <p className="text-[11px] text-slate-400 mt-1">
                      定时任务建议使用小批量增量抓取，降低风控风险。
                    </p>
                  </div>
                </>
              ) : (
                <>
                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1.5 uppercase tracking-wider">
                      打标平台
                    </label>
                    <select
                      value={formTagPlatform}
                      onChange={(e) => setFormTagPlatform(e.target.value)}
                      className={inputCls}
                    >
                      <option value="">全部平台</option>
                      {supportedPlatforms.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                        </option>
                      ))}
                    </select>
                    <p className="text-[11px] text-slate-400 mt-1">
                      仅对尚未打标的收藏内容执行，已打标的不会重复处理。
                    </p>
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <label className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                        AI Agent 配置 <span className="text-red-500">*</span>
                      </label>
                      <button
                        type="button"
                        onClick={() => setShowAgentForm((v) => !v)}
                        className="text-[11px] font-semibold text-indigo-600 hover:text-indigo-800 inline-flex items-center gap-0.5"
                      >
                        <Plus className="w-3 h-3" />
                        {showAgentForm ? '收起' : '新建配置'}
                      </button>
                    </div>
                    <select
                      value={formAgentId}
                      onChange={(e) => setFormAgentId(e.target.value)}
                      className={inputCls}
                      disabled={agents.length === 0}
                    >
                      {agents.length === 0 && <option value="">请先新建 Agent 配置</option>}
                      {agents.map((a) => (
                        <option key={a.agent_id} value={a.agent_id}>
                          {a.name}（{a.model_id}）
                        </option>
                      ))}
                    </select>

                    {showAgentForm && (
                      <div className="mt-3 p-4 bg-slate-50 border border-slate-200 rounded-2xl space-y-3">
                        <p className="text-[11px] text-slate-500">
                          自定义 OpenAI 兼容接口（Base URL / API Key / Model ID），配置保存后可复用。
                        </p>
                        <input
                          type="text"
                          value={agentForm.name}
                          onChange={(e) => setAgentForm((f) => ({ ...f, name: e.target.value }))}
                          placeholder="配置名称，如 DeepSeek / 本地 Ollama"
                          className={inputCls}
                        />
                        <input
                          type="text"
                          value={agentForm.base_url}
                          onChange={(e) => setAgentForm((f) => ({ ...f, base_url: e.target.value }))}
                          placeholder="Base URL，如 https://api.deepseek.com/v1"
                          className={`${inputCls} font-mono text-xs`}
                        />
                        <input
                          type="password"
                          value={agentForm.api_key}
                          onChange={(e) => setAgentForm((f) => ({ ...f, api_key: e.target.value }))}
                          placeholder="API Key"
                          className={`${inputCls} font-mono text-xs`}
                        />
                        <input
                          type="text"
                          value={agentForm.model_id}
                          onChange={(e) => setAgentForm((f) => ({ ...f, model_id: e.target.value }))}
                          placeholder="Model ID，如 deepseek-chat"
                          className={`${inputCls} font-mono text-xs`}
                        />
                        <button
                          type="button"
                          onClick={submitAgent}
                          disabled={agentSaving}
                          className="w-full px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-xs font-bold rounded-xl flex items-center justify-center gap-1.5"
                        >
                          <Plus className="w-3.5 h-3.5" />
                          {agentSaving ? '保存中...' : '保存 Agent 配置'}
                        </button>
                      </div>
                    )}
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1.5 uppercase tracking-wider">
                      单轮打标上限
                    </label>
                    <input
                      type="number"
                      min="1"
                      max="2000"
                      value={formTagLimit}
                      onChange={(e) => setFormTagLimit(Number(e.target.value))}
                      className={inputCls}
                    />
                    <p className="text-[11px] text-slate-400 mt-1">
                      每次触发最多处理多少条未打标内容（分批请求模型），控制耗时与费用。
                    </p>
                  </div>
                </>
              )}

              {formError && (
                <p className="text-xs text-rose-600 flex items-center gap-1">
                  <AlertCircle className="w-3.5 h-3.5" />
                  {formError}
                </p>
              )}

              <div className="pt-2 flex items-center justify-end gap-2.5">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-800 rounded-xl"
                >
                  取消
                </button>
                <button
                  type="submit"
                  disabled={creating}
                  className="px-5 py-2.5 bg-slate-900 hover:bg-slate-800 disabled:opacity-50 text-white text-xs sm:text-sm font-bold rounded-xl shadow-xs flex items-center gap-1.5"
                >
                  <Plus className="w-4 h-4" />
                  {creating ? '创建中...' : '创建计划'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Confirmation */}
      {deleteTarget && (
        <div
          className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 anim-backdrop-enter"
          onClick={() => setDeleteTarget(null)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="anim-modal-enter bg-white w-full max-w-md rounded-[28px] p-6 shadow-2xl border border-slate-100 space-y-4"
          >
            <h3 className="text-lg font-bold text-slate-900">确认删除定时计划？</h3>
            <p className="text-xs text-slate-500 leading-relaxed">
              将停止并删除计划「<strong className="text-slate-800">{deleteTarget.title}</strong>
              」（{deleteTarget.cronExpr}），已产生的任务记录与收藏数据不受影响。
            </p>
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setDeleteTarget(null)}
                className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-800 rounded-xl"
              >
                取消
              </button>
              <button
                type="button"
                onClick={async () => {
                  await onDeleteSchedule(deleteTarget.id);
                  setDeleteTarget(null);
                }}
                className="px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold rounded-xl shadow-xs"
              >
                确认删除
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
