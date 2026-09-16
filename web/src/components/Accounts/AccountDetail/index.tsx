import React, { useState, useEffect } from 'react';
import { Account, TaskRecord, ScrapedItem, ScrapingFormData } from '../../../types';
import { PLATFORMS } from '../../../data/platforms';
import { favoriteFacets } from '../../../api';
import { Clock, Play } from 'lucide-react';
import { AccountDetailHeader } from './Header';
import { AccountInfoCards } from './InfoCards';
import { PlatformOperations } from './PlatformOperations';
import { FolderPicker } from './FolderPicker';
import { ScrapeForm } from './ScrapeForm';
import { ScrapeStream } from './ScrapeStream';
import { TasksTab } from './TasksTab';
import { ClearFavoritesModal } from './ClearFavoritesModal';
import { DeleteAccountModal } from './DeleteAccountModal';

interface AccountDetailProps {
  account: Account;
  onBack: () => void;
  onOpenLoginModal: (account: Account) => void;
  onOpenCookiesModal: (account: Account) => void;
  onCheckHealth: (account: Account) => void;
  onToggleStatus: (account: Account) => void;
  onToggleBrowser: (account: Account) => void;
  onDeleteAccount: (account: Account) => void;
  onFavoritesCleared?: (account: Account) => void;
  recentTasks: TaskRecord[];
  allScrapedItems: ScrapedItem[];
  onTriggerScrape: (formData: ScrapingFormData) => void;
  isScrapingInProgress: boolean;
  streamingItems: ScrapedItem[];
}

/**
 * 账号详情主视图：按功能组合子组件（Header / InfoCards / PlatformOperations /
 * FolderPicker / 抓取工作区 / 确认弹窗），持有跨组件共享的状态：
 * 选中收藏夹目标（FolderPicker ↔ ScrapeForm 联动）与本地库统计（InfoCards ↔ 清空弹窗）。
 */
export const AccountDetail: React.FC<AccountDetailProps> = ({
  account,
  onBack,
  onOpenLoginModal,
  onOpenCookiesModal,
  onCheckHealth,
  onToggleStatus,
  onToggleBrowser,
  onDeleteAccount,
  onFavoritesCleared,
  recentTasks,
  allScrapedItems,
  onTriggerScrape,
  isScrapingInProgress,
  streamingItems,
}) => {
  const platform = PLATFORMS.find((p) => p.id === account.platform) || PLATFORMS[0];

  // 抓取目标收藏夹：预览网格点击与 Bilibili 专属参数输入双向联动
  const [selectedFolderMediaId, setSelectedFolderMediaId] = useState<string>(
    account.folders && account.folders[0] ? account.folders[0].mediaId : ''
  );

  // 本地库实时统计（favorites 表按账号聚合），概览卡片与清空确认框使用
  const [localStats, setLocalStats] = useState<{ total: number; folderCount: number } | null>(null);

  const reloadLocalStats = async () => {
    try {
      const facets = await favoriteFacets(account.id);
      setLocalStats({ total: facets.total, folderCount: facets.folders.length });
    } catch {
      /* 统计失败静默，保留上次数值 */
    }
  };

  useEffect(() => {
    setLocalStats(null);
    reloadLocalStats();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [account.id]);

  // 确认弹窗开关由顶栏「更多菜单」触发
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  // Active subtab inside account detail
  const [activeSubTab, setActiveSubTab] = useState<'scrape' | 'tasks'>('scrape');

  return (
    <div id="account-detail-view" className="space-y-6">
      <AccountDetailHeader
        account={account}
        platform={platform}
        onBack={onBack}
        onOpenLoginModal={onOpenLoginModal}
        onOpenCookiesModal={onOpenCookiesModal}
        onCheckHealth={onCheckHealth}
        onToggleStatus={onToggleStatus}
        onToggleBrowser={onToggleBrowser}
        onRequestClearFavorites={() => setShowClearConfirm(true)}
        onRequestDeleteAccount={() => setShowDeleteConfirm(true)}
      />

      <AccountInfoCards account={account} localStats={localStats} />

      <PlatformOperations account={account} />

      <FolderPicker
        account={account}
        selectedMediaId={selectedFolderMediaId}
        onSelect={setSelectedFolderMediaId}
      />

      {/* Main Workspace: Manual Scraping & Recent Tasks Tabs */}
      <div className="bg-white rounded-[28px] border border-slate-200/80 shadow-2xs overflow-hidden">
        {/* Subtab Header */}
        <div className="flex items-center justify-between border-b border-slate-100 px-6 pt-4 pb-1">
          <div className="flex items-center gap-4">
            <button
              type="button"
              onClick={() => setActiveSubTab('scrape')}
              className={`pb-3 text-sm font-bold border-b-2 transition-colors flex items-center gap-1.5 ${
                activeSubTab === 'scrape'
                  ? 'border-slate-900 text-slate-900'
                  : 'border-transparent text-slate-500 hover:text-slate-800'
              }`}
            >
              <Play className="w-4 h-4" />
              手动触发抓取
            </button>
            <button
              type="button"
              onClick={() => setActiveSubTab('tasks')}
              className={`pb-3 text-sm font-bold border-b-2 transition-colors flex items-center gap-1.5 ${
                activeSubTab === 'tasks'
                  ? 'border-slate-900 text-slate-900'
                  : 'border-transparent text-slate-500 hover:text-slate-800'
              }`}
            >
              <Clock className="w-4 h-4" />
              最近任务记录 ({recentTasks.length})
            </button>
          </div>
          <span className="text-xs text-slate-400 hidden sm:inline-block">
            支持 0 抓取全部、游标续抓与反风控间隔调节
          </span>
        </div>

        {/* Tab 1: Manual Scraping Panel */}
        {activeSubTab === 'scrape' && (
          <div className="p-6">
            <ScrapeForm
              account={account}
              platform={platform}
              selectedFolderMediaId={selectedFolderMediaId}
              onChangeFolderMediaId={setSelectedFolderMediaId}
              isScrapingInProgress={isScrapingInProgress}
              onTriggerScrape={onTriggerScrape}
            />
            <ScrapeStream
              streamingItems={streamingItems}
              isScrapingInProgress={isScrapingInProgress}
            />
          </div>
        )}

        {/* Tab 2: Recent Tasks List for this Account */}
        {activeSubTab === 'tasks' && (
          <div className="p-6">
            <TasksTab recentTasks={recentTasks} />
          </div>
        )}
      </div>

      {showClearConfirm && (
        <ClearFavoritesModal
          account={account}
          localStats={localStats}
          onClose={() => setShowClearConfirm(false)}
          onFavoritesCleared={(acc) => {
            reloadLocalStats();
            onFavoritesCleared?.(acc);
          }}
        />
      )}

      {showDeleteConfirm && (
        <DeleteAccountModal
          account={account}
          onClose={() => setShowDeleteConfirm(false)}
          onDelete={onDeleteAccount}
        />
      )}
    </div>
  );
};
