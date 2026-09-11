import React, { useState } from 'react';
import { 
  Settings, 
  Sliders, 
  FolderOpen, 
  HardDrive, 
  ShieldCheck, 
  Download, 
  RefreshCw, 
  CheckCircle2, 
  Save,
  Sun,
  Moon,
  Palette
} from 'lucide-react';

interface SettingsViewProps {
  onShowToast: (msg: string, type?: 'success' | 'info' | 'error') => void;
  totalItemsCount: number;
  theme: 'light' | 'dark';
  onToggleTheme: () => void;
  onSetTheme: (theme: 'light' | 'dark') => void;
}

export const SettingsView: React.FC<SettingsViewProps> = ({ 
  onShowToast, 
  totalItemsCount,
  theme,
  onToggleTheme,
  onSetTheme
}) => {
  const [profilePath, setProfilePath] = useState('~/.favapi/profiles');
  const [headlessMode, setHeadlessMode] = useState(false);
  const [requestInterval, setRequestInterval] = useState(2.0);
  const [requestTimeout, setRequestTimeout] = useState(30);

  const handleSave = () => {
    onShowToast('系统运行与抓取参数已成功保存！');
  };

  const handleExportJSON = () => {
    onShowToast(`已导出全量 ${totalItemsCount} 条收藏数据为 favapi_export_${Date.now()}.json`);
  };

  const handleExportCSV = () => {
    onShowToast(`已生成 CSV 表格并开始下载`);
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
            管理 Chromium 独立 Profile 存储路径、反风控频控滑块与本地数据备份。
          </p>
        </div>

        <button
          onClick={handleSave}
          className="px-4 py-2 rounded-2xl bg-slate-900 dark:bg-sky-600 text-white text-xs font-semibold hover:bg-slate-800 dark:hover:bg-sky-500 transition-all flex items-center gap-1.5 shadow-sm active:scale-95 cursor-pointer"
        >
          <Save className="w-3.5 h-3.5" />
          保存修改
        </button>
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
