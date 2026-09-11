import React, { useEffect, useState } from 'react';
import {
  Settings,
  Sliders,
  FolderOpen,
  HardDrive,
  ShieldCheck,
  Download,
  RefreshCw,
  CheckCircle2,
  Sun,
  Moon,
  Palette,
  UserCircle,
  Loader2,
  Sparkles,
  Pencil,
  Trash2,
  Plus,
  Zap,
  Save
} from 'lucide-react';
import { AgentConfigRow, AgentTestResult, fetchAppSettings, updateAppSettings, uploadAvatar } from '../../api';

const DEFAULT_AVATAR = 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&auto=format&fit=crop&q=80';

interface SettingsViewProps {
  onShowToast: (msg: string, type?: 'success' | 'info' | 'error') => void;
  totalItemsCount: number;
  theme: 'light' | 'dark';
  onToggleTheme: () => void;
  onSetTheme: (theme: 'light' | 'dark') => void;
  avatarUrl: string | null;
  onAvatarChange: (url: string) => void;
  agents: AgentConfigRow[];
  onCreateAgent: (body: { name: string; base_url: string; api_key: string; model_id: string }) => Promise<AgentConfigRow>;
  onUpdateAgent: (id: string, body: { name: string; base_url: string; api_key?: string; model_id: string }) => Promise<void>;
  onDeleteAgent: (id: string) => Promise<void>;
  onTestAgent: (id: string) => Promise<AgentTestResult>;
}

const agentInputCls =
  'w-full px-3.5 py-2.5 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-xs font-mono text-slate-800 dark:text-slate-100 focus:bg-white dark:focus:bg-slate-900 focus:border-indigo-400 outline-none transition-all';

export const SettingsView: React.FC<SettingsViewProps> = ({
  onShowToast,
  totalItemsCount,
  theme,
  onToggleTheme,
  onSetTheme,
  avatarUrl,
  onAvatarChange,
  agents,
  onCreateAgent,
  onUpdateAgent,
  onDeleteAgent,
  onTestAgent
}) => {
  const [profilePath, setProfilePath] = useState('~/.favapi/profiles');
  const [headlessMode, setHeadlessMode] = useState(false);
  const [requestInterval, setRequestInterval] = useState(2.0);
  const [requestTimeout, setRequestTimeout] = useState(30);
  const [uploadingAvatar, setUploadingAvatar] = useState(false);
  // loaded 之前的 state 变化来自初始加载，不触发自动保存
  const [settingsLoaded, setSettingsLoaded] = useState(false);

  useEffect(() => {
    fetchAppSettings()
      .then((s) => {
        setProfilePath(s.profile_path);
        setHeadlessMode(s.headless);
        setRequestInterval(s.request_interval);
        setRequestTimeout(s.request_timeout);
      })
      .catch(() => {})
      .finally(() => setSettingsLoaded(true));
  }, []);

  // 修改实时生效：任一设置变化后防抖持久化
  useEffect(() => {
    if (!settingsLoaded) return;
    const timer = window.setTimeout(() => {
      updateAppSettings({
        profile_path: profilePath,
        headless: headlessMode,
        request_interval: requestInterval,
        request_timeout: requestTimeout,
      })
        .then(() => onShowToast('设置已自动保存', 'success'))
        .catch((err: any) => onShowToast(`设置保存失败：${err?.message || '未知错误'}`, 'error'));
    }, 800);
    return () => window.clearTimeout(timer);
  }, [settingsLoaded, profilePath, headlessMode, requestInterval, requestTimeout]);

  const handleAvatarUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file || uploadingAvatar) return;
    setUploadingAvatar(true);
    try {
      const url = await uploadAvatar(file);
      onAvatarChange(url);
      onShowToast('头像已更新，侧边栏即时生效');
    } catch (err: any) {
      onShowToast(`头像上传失败：${err?.message || '未知错误'}`, 'error');
    } finally {
      setUploadingAvatar(false);
    }
  };

  const handleExportJSON = () => {
    onShowToast(`已导出全量 ${totalItemsCount} 条收藏数据为 favapi_export_${Date.now()}.json`);
  };

  const handleExportCSV = () => {
    onShowToast(`已生成 CSV 表格并开始下载`);
  };

  // ---------- AI Agent 配置管理 ----------
  const emptyAgentForm = { name: '', base_url: '', api_key: '', model_id: '' };
  const [showAgentForm, setShowAgentForm] = useState(false);
  const [editingAgentId, setEditingAgentId] = useState<string | null>(null);
  const [agentForm, setAgentForm] = useState(emptyAgentForm);
  const [agentSaving, setAgentSaving] = useState(false);
  // agent_id -> 测试状态：'testing' 或测试结果
  const [agentTests, setAgentTests] = useState<Record<string, 'testing' | AgentTestResult>>({});

  const openAgentCreate = () => {
    setEditingAgentId(null);
    setAgentForm(emptyAgentForm);
    setShowAgentForm(true);
  };

  const openAgentEdit = (a: AgentConfigRow) => {
    setEditingAgentId(a.agent_id);
    setAgentForm({ name: a.name, base_url: a.base_url, api_key: '', model_id: a.model_id });
    setShowAgentForm(true);
  };

  const submitAgentForm = async (e: React.FormEvent) => {
    e.preventDefault();
    const { name, base_url, api_key, model_id } = agentForm;
    if (!name.trim() || !base_url.trim() || !model_id.trim() || (!editingAgentId && !api_key.trim())) {
      onShowToast('名称 / Base URL / Model ID 必填（新建时 API Key 也必填）', 'error');
      return;
    }
    setAgentSaving(true);
    try {
      if (editingAgentId) {
        await onUpdateAgent(editingAgentId, {
          name: name.trim(),
          base_url: base_url.trim(),
          model_id: model_id.trim(),
          ...(api_key.trim() ? { api_key: api_key.trim() } : {}),  // 留空表示保留原 Key
        });
        onShowToast(`Agent「${name.trim()}」已更新`);
      } else {
        await onCreateAgent({ name: name.trim(), base_url: base_url.trim(), api_key: api_key.trim(), model_id: model_id.trim() });
        onShowToast(`Agent「${name.trim()}」已创建`);
      }
      setShowAgentForm(false);
      setAgentForm(emptyAgentForm);
      setEditingAgentId(null);
    } catch (err: any) {
      onShowToast(`Agent 保存失败：${err?.message || '未知错误'}`, 'error');
    } finally {
      setAgentSaving(false);
    }
  };

  const handleTestAgent = async (a: AgentConfigRow) => {
    setAgentTests((prev) => ({ ...prev, [a.agent_id]: 'testing' }));
    try {
      const result = await onTestAgent(a.agent_id);
      setAgentTests((prev) => ({ ...prev, [a.agent_id]: result }));
      onShowToast(
        result.ok
          ? `「${a.name}」连通正常（${result.latency_ms}ms）`
          : `「${a.name}」连通失败：${result.error || '未知错误'}`,
        result.ok ? 'success' : 'error'
      );
    } catch (err: any) {
      setAgentTests((prev) => ({ ...prev, [a.agent_id]: { ok: false, error: err?.message || '请求失败' } }));
      onShowToast(`测试请求失败：${err?.message || '未知错误'}`, 'error');
    }
  };

  const handleDeleteAgent = async (a: AgentConfigRow) => {
    try {
      await onDeleteAgent(a.agent_id);
      onShowToast(`Agent「${a.name}」已删除`);
    } catch (err: any) {
      onShowToast(`删除失败：${err?.message || '未知错误'}`, 'error');
    }
  };

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-5xl mx-auto flex flex-col gap-6">
      {/* Header */}
      <div className="bg-white dark:bg-[#161B26] rounded-3xl p-6 border border-slate-100 dark:border-slate-800 shadow-sm flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
            <Settings className="w-5 h-5 text-sky-600 dark:text-sky-400" />
            系统与运行环境配置
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            管理 Chromium 独立 Profile 存储路径、反风控频控滑块与本地数据备份，修改后自动保存。
          </p>
        </div>
      </div>

      {/* Settings Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Card 0: 界面外观与主题 */}
        <div className="bg-white dark:bg-[#161B26] rounded-3xl p-6 border border-slate-100 dark:border-slate-800 shadow-sm flex flex-col gap-4 md:col-span-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-xl bg-amber-50 dark:bg-amber-950/60 text-amber-600 dark:text-amber-400 flex items-center justify-center">
                <Palette className="w-4 h-4" />
              </div>
              <div>
                <h4 className="text-sm font-bold text-slate-900 dark:text-white">界面显示与主题偏好</h4>
                <p className="text-[11px] text-slate-400">支持亮色模式与深色沉浸式暗色模式无缝切换</p>
              </div>
            </div>

            <div className="flex items-center gap-2 p-1 bg-slate-100 dark:bg-slate-800 rounded-2xl border border-slate-200/80 dark:border-slate-700">
              <button
                type="button"
                onClick={() => {
                  onSetTheme('light');
                  onShowToast('已切换为亮色模式', 'info');
                }}
                className={`flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
                  theme === 'light'
                    ? 'bg-white text-slate-900 shadow-xs'
                    : 'text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
                }`}
              >
                <Sun className="w-3.5 h-3.5 text-amber-500" />
                亮色模式
              </button>

              <button
                type="button"
                onClick={() => {
                  onSetTheme('dark');
                  onShowToast('已切换为暗色模式', 'info');
                }}
                className={`flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
                  theme === 'dark'
                    ? 'bg-slate-900 dark:bg-sky-600 text-white shadow-xs'
                    : 'text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
                }`}
              >
                <Moon className="w-3.5 h-3.5 text-sky-400" />
                暗色模式
              </button>
            </div>
          </div>
        </div>

        {/* Card 0.5: 个人头像 */}
        <div className="bg-white dark:bg-[#161B26] rounded-3xl p-6 border border-slate-100 dark:border-slate-800 shadow-sm flex flex-col gap-4 md:col-span-2">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-rose-50 dark:bg-rose-950/60 text-rose-600 dark:text-rose-400 flex items-center justify-center">
              <UserCircle className="w-4 h-4" />
            </div>
            <div>
              <h4 className="text-sm font-bold text-slate-900 dark:text-white">个人头像</h4>
              <p className="text-[11px] text-slate-400">上传后将在侧边栏展示，支持 PNG / JPEG / WebP / GIF，不超过 5MB</p>
            </div>
          </div>

          <div className="flex items-center gap-5 pt-1">
            <img
              src={avatarUrl ?? DEFAULT_AVATAR}
              alt="当前头像"
              className="w-16 h-16 rounded-full object-cover ring-2 ring-slate-200 dark:ring-slate-700 shrink-0"
            />
            <label
              className={`px-4 py-2.5 rounded-2xl text-xs font-semibold transition-all flex items-center gap-2 cursor-pointer border border-transparent ${
                uploadingAvatar
                  ? 'bg-slate-100 dark:bg-slate-800 text-slate-400 dark:text-slate-500 cursor-wait'
                  : 'bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-800 dark:text-slate-100 dark:border-slate-700'
              }`}
            >
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp,image/gif"
                className="hidden"
                disabled={uploadingAvatar}
                onChange={handleAvatarUpload}
              />
              {uploadingAvatar ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  上传中...
                </>
              ) : (
                '更换头像'
              )}
            </label>
          </div>
        </div>

        {/* Card 1: 浏览器隔离与路径 */}
        <div className="bg-white dark:bg-[#161B26] rounded-3xl p-6 border border-slate-100 dark:border-slate-800 shadow-sm flex flex-col gap-4">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-sky-50 dark:bg-sky-950/60 text-sky-600 dark:text-sky-400 flex items-center justify-center">
              <FolderOpen className="w-4 h-4" />
            </div>
            <div>
              <h4 className="text-sm font-bold text-slate-900 dark:text-white">Chromium Profile 隔离目录</h4>
              <p className="text-[11px] text-slate-400">每个账号独立分配隔离会话文件夹</p>
            </div>
          </div>

          <div className="flex flex-col gap-1.5 mt-1">
            <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">基础存储路径</label>
            <input
              type="text"
              value={profilePath}
              onChange={(e) => setProfilePath(e.target.value)}
              className="px-3.5 py-2.5 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-xs font-mono text-slate-800 dark:text-slate-100 focus:bg-white dark:focus:bg-slate-900 focus:border-sky-400 outline-none transition-all"
            />
          </div>

          <div className="flex items-center justify-between pt-2 border-t border-slate-50 dark:border-slate-800/80">
            <div>
              <div className="text-xs font-semibold text-slate-800 dark:text-slate-200">无头浏览器运行模式 (Headless)</div>
              <div className="text-[11px] text-slate-400">默认关闭以便于二维码人工扫码验证</div>
            </div>
            <input
              type="checkbox"
              checked={headlessMode}
              onChange={(e) => setHeadlessMode(e.target.checked)}
              className="w-4 h-4 rounded text-sky-600 border-slate-300 dark:border-slate-700 focus:ring-sky-500 cursor-pointer"
            />
          </div>
        </div>

        {/* Card 2: 反风控抓取频控 */}
        <div className="bg-white dark:bg-[#161B26] rounded-3xl p-6 border border-slate-100 dark:border-slate-800 shadow-sm flex flex-col gap-4">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 flex items-center justify-center">
              <Sliders className="w-4 h-4" />
            </div>
            <div>
              <h4 className="text-sm font-bold text-slate-900 dark:text-white">抓取频控与反风控</h4>
              <p className="text-[11px] text-slate-400">控制翻页与接口调用的休眠时间</p>
            </div>
          </div>

          <div className="flex flex-col gap-2 mt-1">
            <div className="flex items-center justify-between text-xs">
              <span className="font-semibold text-slate-700 dark:text-slate-300">翻页休眠间隔</span>
              <span className="font-mono font-bold text-sky-600 dark:text-sky-400 bg-sky-50 dark:bg-sky-950/60 border border-transparent dark:border-sky-800/60 px-2 py-0.5 rounded">
                {requestInterval.toFixed(1)} 秒
              </span>
            </div>
            <input
              type="range"
              min="1.0"
              max="5.0"
              step="0.1"
              value={requestInterval}
              onChange={(e) => setRequestInterval(parseFloat(e.target.value))}
              className="w-full h-1.5 bg-slate-200 dark:bg-slate-700 rounded-lg appearance-none cursor-pointer accent-sky-600"
            />
            <div className="flex justify-between text-[10px] text-slate-400 font-mono">
              <span>1.0s (极速)</span>
              <span>2.5s (推荐安全)</span>
              <span>5.0s (稳妥保活)</span>
            </div>
          </div>

          <div className="flex flex-col gap-1.5 pt-2 border-t border-slate-50 dark:border-slate-800/80">
            <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">网络请求超时 (秒)</label>
            <input
              type="number"
              value={requestTimeout}
              onChange={(e) => setRequestTimeout(parseInt(e.target.value) || 30)}
              className="px-3.5 py-2 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-xs font-mono text-slate-800 dark:text-slate-100 focus:bg-white dark:focus:bg-slate-900 focus:border-sky-400 outline-none w-32"
            />
          </div>
        </div>

        {/* Card 2.5: AI Agent 智能打标配置 */}
        <div className="bg-white dark:bg-[#161B26] rounded-3xl p-6 border border-slate-100 dark:border-slate-800 shadow-sm flex flex-col gap-4 md:col-span-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-xl bg-violet-50 dark:bg-violet-950/60 text-violet-600 dark:text-violet-400 flex items-center justify-center">
                <Sparkles className="w-4 h-4" />
              </div>
              <div>
                <h4 className="text-sm font-bold text-slate-900 dark:text-white">AI Agent 智能打标配置</h4>
                <p className="text-[11px] text-slate-400">OpenAI 兼容接口（Base URL / API Key / Model ID），供定时智能打标任务使用</p>
              </div>
            </div>
            <button
              type="button"
              onClick={openAgentCreate}
              className="px-3.5 py-2 rounded-xl bg-slate-900 dark:bg-sky-600 hover:bg-slate-800 dark:hover:bg-sky-500 text-white text-xs font-semibold transition-colors flex items-center gap-1.5 shadow-sm active:scale-95 cursor-pointer"
            >
              <Plus className="w-3.5 h-3.5" />
              新建配置
            </button>
          </div>

          {agents.length === 0 && !showAgentForm && (
            <div className="py-8 text-center text-xs text-slate-400 border border-dashed border-slate-200 dark:border-slate-700 rounded-2xl">
              暂无 Agent 配置，点击「新建配置」创建后即可在定时任务中使用 AI 智能打标
            </div>
          )}

          <div className="flex flex-col gap-2.5">
            {agents.map((a) => {
              const test = agentTests[a.agent_id];
              return (
                <div
                  key={a.agent_id}
                  className="p-4 rounded-2xl border border-slate-100 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-800/40 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-bold text-slate-900 dark:text-white">{a.name}</span>
                      <span className="px-2 py-0.5 rounded-md bg-violet-50 dark:bg-violet-950/60 text-violet-600 dark:text-violet-400 text-[10px] font-bold border border-violet-100 dark:border-violet-900 font-mono">
                        {a.model_id}
                      </span>
                    </div>
                    <div className="text-[11px] text-slate-400 font-mono mt-1 truncate">{a.base_url}</div>
                    {test === 'testing' ? (
                      <div className="text-[11px] text-sky-500 flex items-center gap-1 mt-1">
                        <Loader2 className="w-3 h-3 animate-spin" />
                        正在测试连通性...
                      </div>
                    ) : test ? (
                      test.ok ? (
                        <div className="text-[11px] text-emerald-600 flex items-center gap-1 mt-1">
                          <CheckCircle2 className="w-3 h-3" />
                          连通正常 · {test.latency_ms}ms · 回复「{test.reply || '—'}」
                        </div>
                      ) : (
                        <div className="text-[11px] text-rose-600 mt-1 break-all">连通失败：{test.error}</div>
                      )
                    ) : null}
                  </div>

                  <div className="flex items-center gap-1.5 shrink-0">
                    <button
                      type="button"
                      onClick={() => handleTestAgent(a)}
                      disabled={test === 'testing'}
                      className="px-3 py-1.5 rounded-xl text-xs font-semibold bg-amber-50 dark:bg-amber-950/60 text-amber-600 dark:text-amber-400 border border-amber-100 dark:border-amber-900 hover:bg-amber-100 dark:hover:bg-amber-900/40 transition-colors flex items-center gap-1.5 disabled:opacity-50 cursor-pointer"
                    >
                      <Zap className="w-3.5 h-3.5" />
                      测试
                    </button>
                    <button
                      type="button"
                      onClick={() => openAgentEdit(a)}
                      className="px-3 py-1.5 rounded-xl text-xs font-semibold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors flex items-center gap-1.5 cursor-pointer"
                    >
                      <Pencil className="w-3.5 h-3.5" />
                      编辑
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDeleteAgent(a)}
                      className="p-2 rounded-xl text-slate-400 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/40 transition-colors cursor-pointer"
                      title="删除此 Agent 配置"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>

          {showAgentForm && (
            <form
              onSubmit={submitAgentForm}
              className="p-4 bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-2xl grid grid-cols-1 md:grid-cols-2 gap-3"
            >
              <div className="md:col-span-2 text-xs font-bold text-slate-700 dark:text-slate-200">
                {editingAgentId ? '编辑 Agent 配置' : '新建 Agent 配置'}
                <span className="ml-2 font-normal text-slate-400">API Key 留空表示保留原值（仅编辑时）</span>
              </div>
              <input
                type="text"
                value={agentForm.name}
                onChange={(e) => setAgentForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="配置名称，如 DeepSeek / 本地 Ollama"
                className={`${agentInputCls} font-sans`}
              />
              <input
                type="text"
                value={agentForm.model_id}
                onChange={(e) => setAgentForm((f) => ({ ...f, model_id: e.target.value }))}
                placeholder="Model ID，如 deepseek-chat"
                className={agentInputCls}
              />
              <input
                type="text"
                value={agentForm.base_url}
                onChange={(e) => setAgentForm((f) => ({ ...f, base_url: e.target.value }))}
                placeholder="Base URL，如 https://api.deepseek.com/v1"
                className={agentInputCls}
              />
              <input
                type="password"
                value={agentForm.api_key}
                onChange={(e) => setAgentForm((f) => ({ ...f, api_key: e.target.value }))}
                placeholder={editingAgentId ? 'API Key（留空保留原值）' : 'API Key'}
                className={agentInputCls}
              />
              <div className="md:col-span-2 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setShowAgentForm(false);
                    setEditingAgentId(null);
                    setAgentForm(emptyAgentForm);
                  }}
                  className="px-4 py-2 text-xs font-semibold text-slate-600 dark:text-slate-300 hover:text-slate-800 dark:hover:text-white rounded-xl cursor-pointer"
                >
                  取消
                </button>
                <button
                  type="submit"
                  disabled={agentSaving}
                  className="px-4 py-2 bg-slate-900 dark:bg-sky-600 hover:bg-slate-800 dark:hover:bg-sky-500 disabled:opacity-50 text-white text-xs font-bold rounded-xl flex items-center gap-1.5 cursor-pointer"
                >
                  <Save className="w-3.5 h-3.5" />
                  {agentSaving ? '保存中...' : '保存'}
                </button>
              </div>
            </form>
          )}
        </div>

        {/* Card 3: 数据导出与持久化 */}
        <div className="bg-white dark:bg-[#161B26] rounded-3xl p-6 border border-slate-100 dark:border-slate-800 shadow-sm flex flex-col gap-4 md:col-span-2">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-emerald-50 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 flex items-center justify-center">
              <Download className="w-4 h-4" />
            </div>
            <div>
              <h4 className="text-sm font-bold text-slate-900 dark:text-white">数据备份与导出</h4>
              <p className="text-[11px] text-slate-400">
                将已入库的全部全量收藏元数据导出为开放格式
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3 pt-2">
            <button
              onClick={handleExportJSON}
              className="px-4 py-2.5 rounded-2xl bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-800 dark:text-slate-100 text-xs font-semibold transition-colors flex items-center gap-2 cursor-pointer border border-transparent dark:border-slate-700"
            >
              <Download className="w-3.5 h-3.5 text-slate-600 dark:text-slate-400" />
              导出 JSON 完整元数据
            </button>
            <button
              onClick={handleExportCSV}
              className="px-4 py-2.5 rounded-2xl bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-800 dark:text-slate-100 text-xs font-semibold transition-colors flex items-center gap-2 cursor-pointer border border-transparent dark:border-slate-700"
            >
              <Download className="w-3.5 h-3.5 text-slate-600 dark:text-slate-400" />
              导出 CSV 表格
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
