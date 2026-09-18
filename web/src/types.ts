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
  intro?: string;
  cover?: string;
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
  /** 入库来源（收藏列表 / 喜欢列表 / 稍后再看列表…）；空 = 收藏列表 */
  sourceName?: string;
  /** 抓取流条目是否为本次新增（false = 库中已存在，即跳过项）；缺省视为新增 */
  isNew?: boolean;
}

/** 抓取目标表单的一个输入项（后端 /platforms.fetch_targets[].params 下发）。 */
export interface FetchTargetParamSpec {
  key: string;
  label: string;
  type: string; // text | textarea | number | date | select
  required: boolean;
  placeholder: string;
  help: string;
  options?: Array<{ value: string; label: string }>;
}

/** 可抓取入库的列表目标（收藏 / 喜欢 / 稍后再看…），前端渲染卡片 + 弹窗表单。 */
export interface FetchTargetSpec {
  action: string;
  name: string;
  description: string;
  source: string; // 入库来源标记；空 = 收藏列表
  params: FetchTargetParamSpec[];
}

/** 手动抓取请求：目标 action + 后端参数 + 执行模式（替代旧表单模型 ScrapingFormData）。 */
export interface ScrapeRequest {
  action: string; // list_favorites / list_likes / list_watchlater…
  params: Record<string, any>; // key 与 FetchTargetParamSpec.key 对齐，直接传后端
  isAsync: boolean;
}
