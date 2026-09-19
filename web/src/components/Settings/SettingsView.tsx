import React, { useEffect, useRef, useState } from 'react';
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
  Save,
  Maximize2,
  Frame,
  ImageDown,
  RotateCcw,
  Check
} from 'lucide-react';
import { AgentConfigRow, AgentTestResult, backfillCovers, clearAllFavorites, clearDownloadLogs, CoverStatus, DownloaderId, DOWNLOAD_QUALITIES, ToolchainStatus, fetchAppSettings, fetchCoverStatus, fetchToolchain, qualityLabel, updateAppSettings, uploadAvatar } from '../../api';
import { applyPrimaryColor, PRIMARY_PRESETS, readPrimaryColorId } from '../../primaryColor';
import { TerminalDialog } from '../TerminalDialog';
import { confirmDialog } from '../AlertDialog';

interface SettingsViewProps {
  onShowToast: (msg: string, type?: 'success' | 'info' | 'error') => void;
  totalItemsCount: number;
  theme: 'light' | 'dark';
  onToggleTheme: () => void;
  onSetTheme: (theme: 'light' | 'dark') => void;
  fullPage: boolean;
  onSetFullPage: (v: boolean) => void;
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
  fullPage,
  onSetFullPage,
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
  const [downloadDir, setDownloadDir] = useState('');
  const [downloadConcurrency, setDownloadConcurrency] = useState(1);
  const [downloadCategory, setDownloadCategory] = useState('{platform}');
  const [downloadQuality, setDownloadQuality] = useState('auto');
  const [aria2RpcPort, setAria2RpcPort] = useState(6800);
  const [aria2Connections, setAria2Connections] = useState(8);
  const [uploadingAvatar, setUploadingAvatar] = useState(false);
  // 主题色：primaryColor.ts 内联覆盖 <html> 上的 --color-indigo-* 实现全局换色
  const [primaryId, setPrimaryId] = useState(readPrimaryColorId);
  // loaded 之前的 state 变化来自初始加载，不触发自动保存
  const [settingsLoaded, setSettingsLoaded] = useState(false);
  // 加载完成时的基线快照：当前值与基线一致视为无修改，跳过自动保存
  const baselineRef = useRef({
    profile_path: '~/.favapi/profiles',
    headless: false,
    request_interval: 2.0,
    request_timeout: 30,
    download_dir: '',
    download_concurrency: 1,
    download_category: '{platform}',
    download_quality: 'auto',
    aria2_rpc_port: 6800,
    aria2_connections: 8,
  });

  useEffect(() => {
    fetchAppSettings()
      .then((s) => {
        setProfilePath(s.profile_path);
        setHeadlessMode(s.headless);
        setRequestInterval(s.request_interval);
        setRequestTimeout(s.request_timeout);
        setDownloadDir(s.download_dir ?? '');
        setDownloadConcurrency(s.download_concurrency ?? 1);
        setDownloadCategory(s.download_category ?? '{platform}');
        setDownloadQuality(s.download_quality ?? 'auto');
        setAria2RpcPort(s.aria2_rpc_port ?? 6800);
        setAria2Connections(s.aria2_connections ?? 8);
        baselineRef.current = {
          profile_path: s.profile_path,
          headless: s.headless,
          request_interval: s.request_interval,
          request_timeout: s.request_timeout,
          download_dir: (s.download_dir ?? '').trim(),
          download_concurrency: s.download_concurrency ?? 1,
          download_category: (s.download_category ?? '{platform}').trim(),
          download_quality: s.download_quality ?? 'auto',
          aria2_rpc_port: s.aria2_rpc_port ?? 6800,
          aria2_connections: s.aria2_connections ?? 8,
        };
      })
      .catch(() => {})
      .finally(() => setSettingsLoaded(true));
  }, []);

  // 修改实时生效：任一设置变化后防抖持久化
  useEffect(() => {
    if (!settingsLoaded) return;
    const base = baselineRef.current;
    if (
      profilePath === base.profile_path &&
      headlessMode === base.headless &&
      requestInterval === base.request_interval &&
      requestTimeout === base.request_timeout &&
      downloadDir.trim() === base.download_dir &&
      downloadConcurrency === base.download_concurrency &&
      downloadCategory.trim() === base.download_category &&
      downloadQuality === base.download_quality &&
      aria2RpcPort === base.aria2_rpc_port &&
      aria2Connections === base.aria2_connections
    ) {
      return; // 值与加载时一致（未做任何修改），不保存
    }
    const timer = window.setTimeout(() => {
      updateAppSettings({
        profile_path: profilePath,
        headless: headlessMode,
        request_interval: requestInterval,
        request_timeout: requestTimeout,
        download_dir: downloadDir.trim(),
        download_concurrency: downloadConcurrency,
        download_category: downloadCategory.trim(),
        download_quality: downloadQuality,
        aria2_rpc_port: aria2RpcPort,
        aria2_connections: aria2Connections,
      })
        .then(() => onShowToast('设置已自动保存', 'success'))
        .catch((err: any) => onShowToast(`设置保存失败：${err?.message || '未知错误'}`, 'error'));
    }, 800);
    return () => window.clearTimeout(timer);
  }, [settingsLoaded, profilePath, headlessMode, requestInterval, requestTimeout, downloadDir, downloadConcurrency, downloadCategory, downloadQuality, aria2RpcPort, aria2Connections]);

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

  // ---------- 下载工具链检测（yt-dlp / videodl） ----------
  // null = 检测中；installed=false 时提示安装命令，更新按钮变「安装」
  const [toolchain, setToolchain] = useState<Record<DownloaderId, ToolchainStatus | null>>({ 'yt-dlp': null, videodl: null, aria2c: null });
  // 非 null 时打开终端对话框并开始流式安装/更新
  const [terminalTool, setTerminalTool] = useState<DownloaderId | null>(null);

  const refreshToolchain = () => {
    fetchToolchain()
      .then(setToolchain)
      .catch(() => onShowToast('下载工具链检测失败，请确认后端服务正常', 'error'));
  };

  // ---------- 清空下载日志 ----------
  const [clearingLogs, setClearingLogs] = useState(false);

  const handleClearLogs = async () => {
    if (
      !(await confirmDialog({
        title: '清空下载日志',
        message: '该操作不可恢复（运行中任务的日志保留）。',
        confirmText: '清空',
        danger: true,
      }))
    ) return;
    setClearingLogs(true);
    try {
      const { deleted } = await clearDownloadLogs();
      onShowToast(deleted > 0 ? `已清理 ${deleted} 份下载日志` : '没有可清理的日志', deleted > 0 ? 'success' : 'info');
    } catch (err: any) {
      onShowToast(`清理失败：${err?.message || '未知错误'}`, 'error');
    } finally {
      setClearingLogs(false);
    }
  };

  // ---------- 重置收藏夹 ----------
  const [resettingFavs, setResettingFavs] = useState(false);

  const handleResetFavorites = async () => {
    if (
      !(await confirmDialog({
        title: '重置收藏夹',
        message: `将删除本地库全部 ${totalItemsCount} 条收藏及对应内容记录（含 AI 标签），平台云端收藏不受影响，该操作不可恢复。`,
        confirmText: '重置',
        danger: true,
      }))
    ) return;
    setResettingFavs(true);
    try {
      const { deleted, contents_deleted, covers_deleted } = await clearAllFavorites();
      onShowToast(`已重置收藏夹，删除 ${deleted} 条收藏、${contents_deleted} 条内容记录与 ${covers_deleted} 张封面缓存`, 'success');
    } catch (err: any) {
      onShowToast(`重置失败：${err?.message || '未知错误'}`, 'error');
    } finally {
      setResettingFavs(false);
    }
  };

  // ---------- 封面图本地化补齐 ----------
  const [coverChecking, setCoverChecking] = useState(false);
  const [coverStatus, setCoverStatus] = useState<CoverStatus | null>(null);

  const refreshCoverStatus = () => {
    fetchCoverStatus().then(setCoverStatus).catch(() => {});
  };

  // 设置页挂载期间轮询进度（本地 COUNT 查询，开销可忽略）
  useEffect(() => {
    refreshCoverStatus();
    const timer = window.setInterval(refreshCoverStatus, 3000);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleCoverBackfill = async () => {
    if (coverChecking) return;
    setCoverChecking(true);
    try {
      const r = await backfillCovers();
      if (r.missing === 0) {
        onShowToast(`全部 ${r.total} 张封面均已本地化，无需补齐`, 'success');
      } else {
        onShowToast(`发现 ${r.missing} 张缺失封面，已提交 ${r.enqueued} 张到后台下载队列`, 'success');
      }
    } catch (err: any) {
      onShowToast(`封面补齐失败：${err?.message || '未知错误'}`, 'error');
    } finally {
      setCoverChecking(false);
      refreshCoverStatus();
    }
  };

  useEffect(() => {
    refreshToolchain();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

          <div className="flex items-center justify-between pt-4 border-t border-slate-50 dark:border-slate-800/80">
            <div>
              <div className="text-xs font-semibold text-slate-800 dark:text-slate-200">主题色</div>
              <div className="text-[11px] text-slate-400">自定义全局按钮、链接与高亮色，点击即时生效并记忆</div>
            </div>

            <div className="flex items-center gap-2.5">
              {PRIMARY_PRESETS.map((p) => {
                const active = p.id === primaryId;
                return (
                  <button
                    key={p.id}
                    type="button"
                    title={p.name}
                    aria-label={`主题色：${p.name}`}
                    onClick={() => {
                      if (active) return;
                      setPrimaryId(p.id);
                      applyPrimaryColor(p.id);
                      onShowToast(`主题色已切换为「${p.name}」`, 'info');
                    }}
                    className={`w-7 h-7 rounded-full flex items-center justify-center transition-all cursor-pointer ${
                      active
                        ? 'ring-2 ring-offset-2 ring-slate-300 dark:ring-slate-500 dark:ring-offset-[#161B26] scale-110'
                        : 'ring-1 ring-slate-200 dark:ring-slate-700 hover:scale-110'
                    }`}
                    style={{ backgroundColor: p.shades['600'] }}
                  >
                    {active && <Check className="w-3.5 h-3.5 text-white" strokeWidth={3} />}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="flex items-center justify-between pt-4 border-t border-slate-50 dark:border-slate-800/80">
            <div>
              <div className="text-xs font-semibold text-slate-800 dark:text-slate-200">页面布局模式</div>
              <div className="text-[11px] text-slate-400">全屏铺满整个浏览器视口，或保持居中卡片窗口样式</div>
            </div>

            <div className="flex items-center gap-2 p-1 bg-slate-100 dark:bg-slate-800 rounded-2xl border border-slate-200/80 dark:border-slate-700">
              <button
                type="button"
                onClick={() => {
                  onSetFullPage(false);
                  onShowToast('已切换为居中卡片布局', 'info');
                }}
                className={`flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
                  !fullPage
                    ? 'bg-white text-slate-900 shadow-xs'
                    : 'text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
                }`}
              >
                <Frame className="w-3.5 h-3.5 text-amber-500" />
                居中卡片
              </button>

              <button
                type="button"
                onClick={() => {
                  onSetFullPage(true);
                  onShowToast('已切换为全屏铺满布局', 'info');
                }}
                className={`flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
                  fullPage
                    ? 'bg-slate-900 dark:bg-sky-600 text-white shadow-xs'
                    : 'text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
                }`}
              >
                <Maximize2 className="w-3.5 h-3.5 text-sky-400" />
                全屏铺满
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
            {avatarUrl ? (
              <img
                src={avatarUrl}
                alt="当前头像"
                className="w-16 h-16 rounded-full object-cover ring-2 ring-slate-200 dark:ring-slate-700 shrink-0"
              />
            ) : (
              <div className="w-16 h-16 rounded-full bg-rose-50 dark:bg-rose-950/60 flex items-center justify-center ring-2 ring-slate-200 dark:ring-slate-700 shrink-0">
                <UserCircle className="w-8 h-8 text-rose-600 dark:text-rose-400" />
              </div>
            )}
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

        {/* Card 2.2: 下载设置 */}
        <div className="bg-white dark:bg-[#161B26] rounded-3xl p-6 border border-slate-100 dark:border-slate-800 shadow-sm flex flex-col gap-4 md:col-span-2">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-sky-50 dark:bg-sky-950/60 text-sky-600 dark:text-sky-400 flex items-center justify-center">
              <HardDrive className="w-4 h-4" />
            </div>
            <div>
              <h4 className="text-sm font-bold text-slate-900 dark:text-white">收藏下载设置</h4>
              <p className="text-[11px] text-slate-400">
                下载队列的保存位置与并发执行数（yt-dlp / videodl 任务按平台分子目录存放）
              </p>
            </div>
          </div>

          <div className="flex flex-col gap-4 pt-2 border-t border-slate-50 dark:border-slate-800/80">
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                下载分类目录
                <span className="ml-1.5 font-normal text-slate-400">相对下载根目录的子路径，可用变量拼目录结构</span>
              </label>
              <input
                type="text"
                value={downloadCategory}
                onChange={(e) => setDownloadCategory(e.target.value)}
                placeholder="例如 {platform}/{authorName} 或 {platform}/作者-{authorId}"
                className="px-3.5 py-2.5 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-xs font-mono text-slate-800 dark:text-slate-100 focus:bg-white dark:focus:bg-slate-900 focus:border-sky-400 outline-none transition-all"
              />
              <p className="text-[10px] text-slate-400 font-mono">
                可用变量：{'{platform}'}（平台）{'{id}'}（作品 ID）{'{title}'}（标题）{'{ext}'}（扩展名）{'{authorName}'}（作者名，平台下载时可用）{'{authorId}'}（作者 ID）；未知变量按空处理；留空 = {'{platform}'}
              </p>
            </div>
          </div>

          <div className="flex flex-col sm:flex-row sm:items-end gap-4">
            <div className="flex flex-col gap-1.5 flex-1">
              <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                下载保存位置
                <span className="ml-1.5 font-normal text-slate-400">留空使用默认 data/downloads</span>
              </label>
              <input
                type="text"
                value={downloadDir}
                onChange={(e) => setDownloadDir(e.target.value)}
                placeholder="例如 D:/Favorites（相对路径相对程序目录）"
                className="px-3.5 py-2.5 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-xs font-mono text-slate-800 dark:text-slate-100 focus:bg-white dark:focus:bg-slate-900 focus:border-sky-400 outline-none transition-all"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">并发下载数</label>
              <div className="flex items-center gap-1 p-1 bg-slate-100 dark:bg-slate-800 rounded-2xl border border-slate-200/80 dark:border-slate-700">
                {[1, 2, 3].map((n) => (
                  <button
                    key={n}
                    type="button"
                    onClick={() => setDownloadConcurrency(n)}
                    className={`px-4 py-1.5 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
                      downloadConcurrency === n
                        ? 'bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-xs'
                        : 'text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
                    }`}
                  >
                    {n} 路
                  </button>
                ))}
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                下载清晰度
                <span className="ml-1.5 font-normal text-slate-400">平台下载默认档位，下载弹窗可临时改</span>
              </label>
              <select
                value={downloadQuality}
                onChange={(e) => setDownloadQuality(e.target.value)}
                className="px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-xs font-semibold text-slate-700 dark:text-slate-200 bg-white dark:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-400 cursor-pointer w-fit"
                title="auto = 平台推荐画质；指定高度时无精确档回落不超标的最高档"
              >
                {DOWNLOAD_QUALITIES.map((q) => (
                  <option key={q} value={q}>{qualityLabel(q)}</option>
                ))}
              </select>
            </div>
          </div>

          {/* aria2c（平台下载引擎）设置 */}
          <div className="flex flex-col sm:flex-row sm:items-end gap-4 pt-4 border-t border-slate-50 dark:border-slate-800/80">
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                aria2c RPC 端口
                <span className="ml-1.5 font-normal text-slate-400">本机已有 aria2 服务时直接复用</span>
              </label>
              <input
                type="number"
                value={aria2RpcPort}
                onChange={(e) => setAria2RpcPort(parseInt(e.target.value) || 6800)}
                min={1024}
                max={65535}
                className="px-3.5 py-2 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-xs font-mono text-slate-800 dark:text-slate-100 focus:bg-white dark:focus:bg-slate-900 focus:border-sky-400 outline-none w-32"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                单任务连接数
                <span className="ml-1.5 font-normal text-slate-400">多连接分片加速（1-16）</span>
              </label>
              <input
                type="number"
                value={aria2Connections}
                onChange={(e) => setAria2Connections(parseInt(e.target.value) || 8)}
                min={1}
                max={16}
                className="px-3.5 py-2 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-xs font-mono text-slate-800 dark:text-slate-100 focus:bg-white dark:focus:bg-slate-900 focus:border-sky-400 outline-none w-32"
              />
            </div>
          </div>

          {/* 下载工具链检测 */}
          <div className="flex flex-col gap-2.5 pt-4 border-t border-slate-50 dark:border-slate-800/80">
            {(['yt-dlp', 'videodl', 'aria2c'] as const).map((tool) => {
              const st = toolchain[tool];
              return (
                <div key={tool} className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2 min-w-0 flex-wrap">
                    <span className="text-xs font-bold font-mono text-slate-800 dark:text-slate-200">{tool}</span>
                    {st === null ? (
                      <span className="text-[11px] text-slate-400 flex items-center gap-1">
                        <Loader2 className="w-3 h-3 animate-spin" />
                        检测中...
                      </span>
                    ) : st.installed ? (
                      <span className="text-[11px] text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
                        <CheckCircle2 className="w-3 h-3 shrink-0" />
                        已安装 · {st.version ?? '未知版本'}
                      </span>
                    ) : (
                      <span className="text-[11px] text-rose-500 dark:text-rose-400">
                        未安装（pip install {tool === 'videodl' ? 'videofetch' : tool === 'aria2c' ? 'aria2p' : 'yt-dlp'}
                        {tool === 'aria2c' ? '，另需系统安装 aria2c（winget install aria2.aria2）' : ''}）
                      </span>
                    )}
                  </div>

                  <button
                    type="button"
                    onClick={() => setTerminalTool(tool)}
                    disabled={terminalTool !== null || st === null}
                    className="px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 border border-transparent dark:border-slate-700 transition-colors flex items-center gap-1.5 shrink-0 disabled:opacity-50 cursor-pointer"
                  >
                    <RefreshCw className="w-3.5 h-3.5" />
                    {st?.installed ? '检查更新' : '安装'}
                  </button>
                </div>
              );
            })}
          </div>

          {/* 下载日志清理 */}
          <div className="flex items-center justify-between gap-3 pt-4 border-t border-slate-50 dark:border-slate-800/80">
            <div>
              <div className="text-xs font-semibold text-slate-800 dark:text-slate-200">下载日志清理</div>
              <div className="text-[11px] text-slate-400">每个下载任务在 .logs 目录落盘一份日志，清理后不可恢复</div>
            </div>
            <button
              type="button"
              onClick={handleClearLogs}
              disabled={clearingLogs}
              className="px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-rose-50 dark:bg-rose-950/60 text-rose-600 dark:text-rose-400 border border-rose-100 dark:border-rose-900 hover:bg-rose-100 dark:hover:bg-rose-900/40 transition-colors flex items-center gap-1.5 shrink-0 disabled:opacity-50 cursor-pointer"
            >
              <Trash2 className="w-3.5 h-3.5" />
              {clearingLogs ? '清理中...' : '清空下载日志'}
            </button>
          </div>

          {/* 封面图本地化补齐 */}
          <div className="flex flex-col gap-2.5 pt-4 border-t border-slate-50 dark:border-slate-800/80">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-xs font-semibold text-slate-800 dark:text-slate-200">封面图本地化补齐</div>
                <div className="text-[11px] text-slate-400">检查封面本地缓存状态并更新到数据库，缺失的由后台队列自动下载，避免图片链接过期</div>
              </div>
              <button
                type="button"
                onClick={handleCoverBackfill}
                disabled={coverChecking}
                className="px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-sky-50 dark:bg-sky-950/60 text-sky-600 dark:text-sky-400 border border-sky-100 dark:border-sky-900 hover:bg-sky-100 dark:hover:bg-sky-900/40 transition-colors flex items-center gap-1.5 shrink-0 disabled:opacity-50 cursor-pointer"
              >
                {coverChecking ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <ImageDown className="w-3.5 h-3.5" />}
                {coverChecking ? '检查中...' : '检查并补齐封面'}
              </button>
            </div>

            {coverStatus && coverStatus.total > 0 && (
              <div className="flex flex-col gap-1">
                <div className="flex items-center justify-between gap-3 text-[11px]">
                  <span className="text-slate-500 dark:text-slate-400">
                    已本地化{' '}
                    <span className="font-bold text-sky-600 dark:text-sky-400">{coverStatus.localized}</span> / {coverStatus.total}
                  </span>
                  {coverStatus.missing > 0 ? (
                    coverStatus.queue_size > 0 ? (
                      <span className="flex items-center gap-1 text-slate-400 min-w-0 shrink-0">
                        <Loader2 className="w-3 h-3 animate-spin" />
                        后台下载中，队列剩余 {coverStatus.queue_size} 张
                      </span>
                    ) : (
                      <span className="text-slate-400 shrink-0">待补齐 {coverStatus.missing} 张（点击按钮重新检查）</span>
                    )
                  ) : (
                    <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400 shrink-0">
                      <CheckCircle2 className="w-3 h-3" />
                      全部封面已本地化
                    </span>
                  )}
                </div>
                <div className="h-1.5 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-sky-500 transition-all duration-500"
                    style={{ width: `${Math.min(100, (coverStatus.localized / coverStatus.total) * 100)}%` }}
                  />
                </div>
              </div>
            )}
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

          {/* 重置收藏夹 */}
          <div className="flex items-center justify-between gap-3 pt-2 border-t border-slate-50 dark:border-slate-800/80">
            <div>
              <div className="text-xs font-semibold text-slate-800 dark:text-slate-200">重置收藏夹</div>
              <div className="text-[11px] text-slate-400">清空本地库全部 {totalItemsCount} 条收藏及对应内容记录（云端不受影响，可重新抓取恢复）</div>
            </div>
            <button
              type="button"
              onClick={handleResetFavorites}
              disabled={resettingFavs}
              className="px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-rose-50 dark:bg-rose-950/60 text-rose-600 dark:text-rose-400 border border-rose-100 dark:border-rose-900 hover:bg-rose-100 dark:hover:bg-rose-900/40 transition-colors flex items-center gap-1.5 shrink-0 disabled:opacity-50 cursor-pointer"
            >
              {resettingFavs ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RotateCcw className="w-3.5 h-3.5" />}
              {resettingFavs ? '重置中...' : '重置收藏夹'}
            </button>
          </div>
        </div>
      </div>

      {/* 下载工具链安装/更新终端（流式输出） */}
      <TerminalDialog
        downloader={terminalTool}
        onClose={() => setTerminalTool(null)}
        onFinished={refreshToolchain}
      />
    </div>
  );
};
