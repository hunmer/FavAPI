export type PrimaryTab = 'accounts' | 'tasks' | 'data';

export type NavTab = 'dashboard' | 'accounts' | 'data' | 'tasks' | 'schedule' | 'downloads' | 'settings';

export interface ScheduledSync {
  id: string;
  title: string;
  platform: PlatformId;
  accountId: string;
  accountName: string;
  cronExpr: string;
  nextRunTime: string;
  targetFolder?: string;
  status: 'active' | 'paused';
  itemCount?: number;
  action?: string;  // list_favorites / ai_tag
}

/** 平台标识由后端动态提供，自定义平台无需修改前端类型。 */
export type PlatformId = string;

export type AccountStatus = 'active' | 'expired' | 'disabled' | 'logging_in';

export interface BilibiliFolder {
  id: string;
  name: string;
  count: number;
  mediaId: string;
  isDefault?: boolean;
}

export interface Account {
  id: string;
  name: string;
  platform: PlatformId;
  status: AccountStatus;
  lastLoginTime: string;
  lastUsedTime: string;
  browserProfilePath: string;
  // Platform-specific extra details (e.g. Bilibili)
  ownerNickname?: string;
  ownerAvatar?: string;
  ownerUid?: string;
  folders?: BilibiliFolder[];
  isBrowserOpen?: boolean;
}

export interface CookieItem {
  name: string;
  value: string;
  domain: string;
  path: string;
  expires: string;
  secure: boolean;
  httpOnly: boolean;
}

export type TaskStatus = 'running' | 'success' | 'failed';
export type OperationType = '增量抓取' | '全量抓取' | '登录态检查' | '会话续期' | '智能打标';

export interface TaskRecord {
  id: string;
  startTime: string;
  durationSec: number;
  platform: PlatformId;
  accountId: string;
  accountName: string;
  operationType: OperationType;
  status: TaskStatus;
  scrapedCount: number;
  newCount: number;
  errorMessage?: string;
  cursor?: string;
}

export interface ScrapedItem {
  id: string;
  title: string;
  url: string;
  author: string;
  authorAvatar?: string;
  duration?: string;
  likes: number;
  favorites: number;
  folderName: string;
  mediaId?: string;
  favTime: string;
  crawlTime: string;
  coverUrl: string;
  platform: PlatformId;
  accountId: string;
  accountName: string;
  tags?: string[];
  notes?: string;
  description?: string;
}

export interface ScrapingFormData {
  count: number; // 0 = all
  startCursor: string;
  isAsync: boolean;
  // Bilibili specific
  folderUrlOrUid?: string;
  mediaId?: string;
  pageIntervalSec?: number; // e.g. 1.5 ~ 5.0
  // Xiaohongshu specific
  profileUrlOrUid?: string;
  // WeChat specific
  jsonPath?: string;
}
