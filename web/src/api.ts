/**
 * FavAPI 后端 (/api/v1) 接口封装 + 控制台 UI 类型映射。
 * 后端字段（snake_case）在这里统一转换为组件使用的 console 类型（types.ts）。
 */
import { Account, BilibiliFolder, CookieItem, FetchTargetSpec, PlatformId, ScheduledSync, ScrapeRequest, ScrapedItem, TaskRecord } from './types';

const BASE = '/api/v1';

async function request<T = any>(path: string, opts: RequestInit = {}): Promise<T> {
  const headers = opts.body instanceof FormData ? { ...(opts.headers || {}) } : { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  const res = await fetch(`${BASE}${path}`, {
    headers,
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error((data as any).detail || res.statusText);
    (err as any).status = res.status;
    throw err;
  }
  return data as T;
}

// ---------- 后端行类型 ----------

export interface AccountRow {
  account_id: string;
  platform: PlatformId;
  name: string;
  status: string;             // active / expired / disabled
  profile_path?: string | null;
  last_login_at?: string | null;
  last_used_at?: string | null;
  created_at?: string | null;
  extra?: Record<string, any>;
  logging_in?: boolean;
  avatar?: string | null;  // 后端统一提取 extra.{platform}.owner.avatar（已本地化防过期）
}

export interface TaskRow {
  task_id: string;
  account_id?: string | null;
  platform?: PlatformId | null;
  action?: string | null;
  request_params?: Record<string, any>;
  status?: string | null;     // pending / running / success / failed
  result_count?: number | null;
  new_favorites?: number | null;
  error_message?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface FavoriteRow {
  content_id: string;
  account_id?: string | null;
  platform: PlatformId;
  title?: string | null;
  author_name?: string | null;
  cover_url?: string | null;
  duration?: number | null;
  statistics?: Record<string, any>;
  fav_media_id?: string | null;
  fav_title?: string | null;
  source?: string | null; // 入库来源（空 = 收藏列表）
  collected_at?: string | null;
  fetched_at?: string | null;
  url?: string | null;
  tags?: string[];
  tagged_at?: string | null;
}

export interface AgentConfigRow {
  agent_id: string;
  name: string;
  base_url: string;
  api_key: string;
  model_id: string;
  created_at?: string | null;
}

export interface ScheduleRow {
  schedule_id: string;
  title?: string | null;
  account_id: string;
  platform: PlatformId;
  action: string;
  params?: Record<string, any>;
  cron_expr: string;
  status: 'active' | 'paused';
  last_run_at?: string | null;
  next_run_at?: string | null;
  last_task_id?: string | null;
  created_at?: string | null;
}

export interface OperationParamSpec {
  key: string;
  label: string;
  type: string; // text | textarea | number | date | select
  required: boolean;
  placeholder: string;
  help: string;
  options?: Array<{ value: string; label: string }>;
}

export interface OperationSpec {
  op_id: string;
  name: string;
  description: string;
  danger: boolean;
  params: OperationParamSpec[];
}

export interface PlatformInfoRow {
  platform: PlatformId;
  display_name: string;
  implemented: boolean;
  supported_actions: string[];
  icon_url?: string;
  api_fetch_implemented?: boolean;
  api_operations?: OperationSpec[];
  fetch_targets?: FetchTargetSpec[];
  /** 是否提供「平台下载」（按视频 ID 解析直链 → aria2c） */
  download_api_implemented?: boolean;
}

// ---------- 工具 ----------

function fmtDateTime(iso?: string | null): string {
  if (!iso) return '—';
  return iso.replace('T', ' ').slice(0, 19);
}

function fmtDuration(sec?: number | null): string {
  if (sec == null || sec < 0) return '—';
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return m > 0 ? `${m}:${String(s).padStart(2, '0')}` : `0:${String(s).padStart(2, '0')}`;
}

function parseTime(iso?: string | null): number {
  return iso ? new Date(iso).getTime() : NaN;
}

// ---------- 映射到 UI 类型 ----------

export function toAccount(row: AccountRow, browserOpen: Set<string> = new Set()): Account {
  const extra = row.extra || {};
  // 平台身份信息由 adapter 登录/抓取后写入 extra.{platform}.owner（bilibili 含收藏夹列表）
  const biliOwner = extra.bilibili?.owner || {};
  const xhsOwner = extra.xiaohongshu?.owner || {};
  const dyOwner = extra.douyin?.owner || {};
  const thOwner = extra.threads?.owner || {};
  const ttOwner = extra.tiktok?.owner || {};
  const folders: BilibiliFolder[] | undefined = Array.isArray(extra.bilibili?.folders)
    ? extra.bilibili.folders.map((f: any) => ({
        id: String(f.media_id ?? ''),
        name: f.title || '',
        count: f.media_count ?? 0,
        mediaId: String(f.media_id ?? ''),
        isDefault: f.title === '默认收藏夹',
        intro: f.intro || '',
        cover: f.cover || '',
      }))
    : undefined;
  return {
    id: row.account_id,
    name: row.name,
    platform: row.platform,
    status: (row.logging_in ? 'logging_in' : row.status) as Account['status'],
    lastLoginTime: fmtDateTime(row.last_login_at),
    lastUsedTime: fmtDateTime(row.last_used_at),
    browserProfilePath: row.profile_path || '',
    ownerNickname:
      biliOwner.name || xhsOwner.nickname || dyOwner.nickname || thOwner.username || ttOwner.nickname || extra.nickname,
    ownerAvatar: row.avatar || extra.avatar,
    ownerUid:
      biliOwner.mid || xhsOwner.user_id || dyOwner.uid || thOwner.id || ttOwner.user_id || extra.uid,
    folders,
    isBrowserOpen: browserOpen.has(row.account_id),
  };
}

export function toTask(row: TaskRow, accountNameById: Map<string, string>): TaskRecord {
  const params = row.request_params || {};
  const operation =
    row.action === 'list_favorites'
      ? Number(params.count) === 0 ? '全量抓取' : '增量抓取'
      : row.action === 'ai_tag'
        ? '智能打标'
        : (row.action || '未知操作');
  const durSec = Math.max(
    0,
    Math.round((parseTime(row.finished_at) - parseTime(row.started_at)) / 1000) || 0
  );
  return {
    id: row.task_id,
    startTime: fmtDateTime(row.started_at),
    durationSec: durSec,
    platform: (row.platform || 'douyin') as PlatformId,
    accountId: row.account_id || '',
    accountName: accountNameById.get(row.account_id || '') || row.account_id || '—',
    operationType: operation as TaskRecord['operationType'],
    status: (row.status === 'pending' ? 'running' : row.status || 'failed') as TaskRecord['status'],
    scrapedCount: row.result_count ?? 0,
    newCount: row.new_favorites ?? row.result_count ?? 0,
    errorMessage: row.error_message || undefined,
  };
}

export function toScrapedItem(row: FavoriteRow, accountNameById: Map<string, string>): ScrapedItem {
  const stats = row.statistics || {};
  return {
    id: row.content_id,
    title: row.title || row.content_id,
    url: row.url || '',
    author: row.author_name || '—',
    // 抖音的 duration 存的是毫秒，格式化前先转秒
    duration: row.duration
      ? fmtDuration(row.platform === 'douyin' ? row.duration / 1000 : row.duration)
      : undefined,
    likes: stats.digg_count ?? stats.like_count ?? 0,
    favorites: stats.collect_count ?? 0,
    folderName: row.fav_title || '默认收藏夹',
    mediaId: row.fav_media_id || undefined,
    favTime: fmtDateTime(row.collected_at),
    crawlTime: fmtDateTime(row.fetched_at),
    coverUrl: row.cover_url || '',
    platform: row.platform,
    accountId: row.account_id || '',
    accountName: accountNameById.get(row.account_id || '') || '—',
    tags: row.tags || [],
    sourceName: row.source || '收藏列表',
  };
}

export function toSchedule(row: ScheduleRow, accountNameById: Map<string, string>): ScheduledSync {
  const isAiTag = row.action === 'ai_tag';
  return {
    id: row.schedule_id,
    title: row.title || (isAiTag ? 'AI 智能打标' : '定时抓取'),
    platform: row.platform,
    accountId: row.account_id,
    accountName: isAiTag
      ? row.params?.platform ? `智能打标 · ${row.params.platform}` : '智能打标 · 全平台'
      : (accountNameById.get(row.account_id) || row.account_id),
    cronExpr: row.cron_expr,
    nextRunTime: row.status === 'active' ? fmtDateTime(row.next_run_at) : '已暂停',
    targetFolder: row.params?.fav_title,
    status: row.status,
    action: row.action,
  };
}

// ---------- 平台 / 账号 ----------

export async function listPlatforms(): Promise<PlatformInfoRow[]> {
  const data = await request<{ platforms: PlatformInfoRow[] }>('/platforms');
  return data.platforms;
}

/** 提供「平台下载」能力的平台集合（模块级缓存，失败回落空集合 = 全部不可平台下载）。 */
export async function fetchPlatformDownloadSet(): Promise<Set<string>> {
  try {
    const platforms = await listPlatforms();
    return new Set(platforms.filter((p) => p.download_api_implemented).map((p) => p.platform));
  } catch {
    return new Set();
  }
}

/** 执行平台 API 操作（写操作/管理类，同步返回结果）。 */
export async function executeOperation(
  accountId: string,
  opId: string,
  params: Record<string, any>
): Promise<Record<string, any>> {
  return request(`/accounts/${accountId}/operations/${opId}`, {
    method: 'POST',
    body: JSON.stringify({ params }),
  });
}

export interface OperationStreamEvent {
  type: 'stage' | 'matched' | 'progress' | 'done' | 'error' | 'canceled';
  stage?: string;
  page?: number;
  total_fetched?: number;
  matched?: number;
  items?: Array<{ content_id?: string; title?: string | null; collected_at?: string | null }>;
  batch_no?: number;
  total_batches?: number;
  done?: number;
  ids?: string[];
  // 日期区间管道式取消的进度字段
  oldest_collected_at?: string | null;
  fetched_this_page?: number;
  matched_this_page?: number;
  canceled?: number;
  result?: Record<string, any>;
  message?: string;
}

/** SSE 流式执行平台 API 操作：阶段进度逐条回调，结束返回 done 事件；失败抛错。传入 signal 可中途取消（后端随连接断开中止执行）。 */
export async function executeOperationStream(
  accountId: string,
  opId: string,
  params: Record<string, any>,
  onEvent: (ev: OperationStreamEvent) => void,
  signal?: AbortSignal
): Promise<OperationStreamEvent> {
  const res = await fetch(`${BASE}/accounts/${accountId}/operations/${opId}/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ params }),
    signal,
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error((data as any).detail || res.statusText);
  }
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let doneEv: OperationStreamEvent | null = null;

  while (true) {
    const { value, done: finished } = await reader.read();
    if (finished) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const chunk = buffer.slice(0, idx).trim();
      buffer = buffer.slice(idx + 2);
      if (!chunk.startsWith('data:')) continue;
      let ev: OperationStreamEvent;
      try {
        ev = JSON.parse(chunk.slice(5).trim());
      } catch {
        continue;
      }
      if (ev.type === 'error') throw new Error(ev.message || '操作执行失败');
      onEvent(ev);
      if (ev.type === 'done') doneEv = ev;
    }
  }
  return doneEv || { type: 'done' };
}

export async function listAccounts(): Promise<AccountRow[]> {
  const data = await request<{ accounts: AccountRow[] }>('/accounts');
  return data.accounts;
}

export async function createAccount(platform: string, name: string): Promise<AccountRow> {
  return request('/accounts', { method: 'POST', body: JSON.stringify({ platform, name }) });
}

export async function patchAccount(accountId: string, body: Record<string, any>): Promise<AccountRow> {
  return request(`/accounts/${accountId}`, { method: 'PATCH', body: JSON.stringify(body) });
}

export async function deleteAccount(accountId: string) {
  return request(`/accounts/${accountId}`, { method: 'DELETE' });
}

/** 发起扫码登录（后端打开有头浏览器），返回后轮询 loginStatus 直到结束。 */
export async function startLogin(accountId: string) {
  return request(`/accounts/${accountId}/login`, { method: 'POST' });
}

export interface LoginStatus {
  logged_in: boolean | null;
  status: string;
  logging_in: boolean;
  busy?: boolean;
  /** refresh=true 且登录有效时是否成功回填了身份（平台不支持时 False） */
  profile_refreshed?: boolean;
}

export async function loginStatus(accountId: string, refresh = false): Promise<LoginStatus> {
  return request(`/accounts/${accountId}/status${refresh ? '?refresh=true' : ''}`);
}

export async function closeLogin(accountId: string) {
  return request<{ closed: boolean }>(`/accounts/${accountId}/login/close`, { method: 'POST' });
}

/** 编辑 Bilibili 收藏夹（FolderPicker dots 菜单），返回同步后的收藏夹列表。 */
export async function editBilibiliFolder(
  accountId: string,
  payload: { media_id: string; title: string; intro?: string; privacy?: number }
): Promise<{ account_id: string; folders: BilibiliFolder[] }> {
  return request(`/accounts/${accountId}/folders/edit`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/** 删除 Bilibili 收藏夹（不可恢复），返回同步后的收藏夹列表。 */
export async function deleteBilibiliFolder(
  accountId: string,
  mediaId: string
): Promise<{ account_id: string; folders: BilibiliFolder[] }> {
  return request(`/accounts/${accountId}/folders/del`, {
    method: 'POST',
    body: JSON.stringify({ media_id: mediaId }),
  });
}

export async function toggleBrowse(accountId: string, url?: string) {
  // 带 url 时为【账号打开】语义：已打开则导航到该地址，不执行关闭切换
  const qs = url ? `?url=${encodeURIComponent(url)}` : '';
  return request<{ opened?: boolean; navigated?: boolean; tab?: boolean }>(`/accounts/${accountId}/browse${qs}`, {
    method: 'POST',
  });
}

export async function browseStatus(accountId: string): Promise<{ opened: boolean }> {
  return request(`/accounts/${accountId}/browse`);
}

export async function getCookieItems(accountId: string): Promise<CookieItem[]> {
  const snap = await request<{ cookies: any[] }>(`/accounts/${accountId}/cookies`);
  return (snap.cookies || []).map((c) => ({
    name: c.name || '',
    value: c.value || '',
    domain: c.domain || '',
    path: c.path || '/',
    expires: typeof c.expires === 'number' ? new Date(c.expires * 1000).toISOString().slice(0, 19) : 'Session',
    secure: false,
    httpOnly: false,
  }));
}

// ---------- 批量身份刷新 ----------

export interface RefreshProfilesResult {
  ok: number;
  failed: number;
  results: Array<{ account_id: string; name: string; status: 'ok' | 'skipped' | 'failed'; detail: string }>;
}

/** 批量身份刷新的实时进度（当前刷新到哪个账号）；done 从 0 计。 */
export interface ProfileRefreshProgress {
  accountId: string;
  done: number;
  total: number;
}

/** 批量刷新账号身份信息（昵称/头像/收藏夹）；串行执行，账号多时耗时较长。 */
export async function refreshProfiles(): Promise<RefreshProfilesResult> {
  return request('/accounts/refresh-profile', { method: 'POST' });
}

export async function refreshProfile(accountId: string) {
  return request<{ account_id: string; status: string }>(`/accounts/${accountId}/refresh-profile`, { method: 'POST' });
}

// ---------- 任务 / 数据 ----------

export async function listTasks(limit = 100, accountId?: string): Promise<TaskRow[]> {
  const q = accountId ? `?limit=${limit}&account_id=${encodeURIComponent(accountId)}` : `?limit=${limit}`;
  const data = await request<{ tasks: TaskRow[] }>(`/tasks${q}`);
  return data.tasks;
}

export async function clearTasks(): Promise<{ deleted: number }> {
  return request('/tasks', { method: 'DELETE' });
}

// ---------- 统计 ----------

export interface StatsData {
  accounts_total: number;
  accounts_active: number;
  favorites_total: number;
  contents_total: number;
  contents_tagged: number;
  today_new_favorites: number;
  tasks_running: number;
  tasks_today: number;
  schedules_active: number;
  db_size_bytes: number;
  data_dir_size_bytes: number;
}

export async function getStats(): Promise<StatsData> {
  return request('/stats');
}

export async function getTask(taskId: string): Promise<TaskRow> {
  return request(`/tasks/${taskId}`);
}

export interface FavoriteListOpts {
  accountId?: string;
  platform?: string;
  folder?: string;
  author?: string;
  source?: string;
  dateStart?: string;
  dateEnd?: string;
  pubStart?: string;
  pubEnd?: string;
  tags?: string[];
  q?: string;
  limit?: number;
  offset?: number;
}

export async function listFavorites(opts: FavoriteListOpts = {}): Promise<{ total: number; items: FavoriteRow[] }> {
  const p = new URLSearchParams({ limit: String(opts.limit ?? 5000), offset: String(opts.offset ?? 0) });
  if (opts.accountId) p.set('account_id', opts.accountId);
  if (opts.platform) p.set('platform', opts.platform);
  if (opts.folder) p.set('folder', opts.folder);
  if (opts.author) p.set('author', opts.author);
  if (opts.source) p.set('source', opts.source);
  if (opts.dateStart) p.set('date_start', opts.dateStart);
  if (opts.dateEnd) p.set('date_end', opts.dateEnd);
  if (opts.pubStart) p.set('pub_start', opts.pubStart);
  if (opts.pubEnd) p.set('pub_end', opts.pubEnd);
  if (opts.tags?.length) p.set('tags', opts.tags.join(','));
  if (opts.q) p.set('q', opts.q);
  return request(`/favorites?${p.toString()}`);
}

// ---------- 数据浏览过滤面板候选 ----------

export interface FacetRow {
  total: number;
  accounts: Array<{ id: string; count: number }>;
  folders: Array<{ name: string; count: number }>;
  sources: Array<{ name: string; count: number }>;
  authors: Array<{ name: string; count: number }>;
}

export async function favoriteFacets(accountId?: string, folder?: string): Promise<FacetRow> {
  const p = new URLSearchParams();
  if (accountId) p.set('account_id', accountId);
  if (folder) p.set('folder', folder);
  return request(`/favorites/facets?${p.toString()}`);
}

// ---------- 抓取 ----------

export async function uploadWechatJson(accountId: string, file: File): Promise<{ json_path: string }> {
  const body = new FormData(); body.append('file', file);
  return request<{ json_path: string }>(`/accounts/${accountId}/wechat-import`, { method: 'POST', body });
}

/** 异步抓取：立即返回 pending 任务，由调用方轮询。action/params 来自抓取目标卡片表单。 */
export async function fetchAsync(platform: string, accountId: string, req: ScrapeRequest) {
  return request<{ task_id: string; status: string }>('/fetch', {
    method: 'POST',
    body: JSON.stringify({
      platform,
      account_id: accountId,
      action: req.action,
      params: req.params,
      async_run: true,
    }),
  });
}

export interface StreamEvent {
  type: 'task' | 'items' | 'done' | 'error';
  task_id?: string;
  items?: Array<{ content_id: string; title?: string; author_name?: string; cover_url?: string | null; url?: string | null; duration?: number; fav_title?: string | null; collected_at?: string; is_new?: boolean }>;
  new_count?: number;
  total_fetched?: number;
  result_count?: number;
  new_favorites?: number;
  cursor?: string;
  error_message?: string;
  folder?: string;
}

/** SSE 流式抓取：逐批回调，结束返回 done 载荷；抛错对应 error 事件。 */
export async function fetchStream(
  platform: string,
  accountId: string,
  req: ScrapeRequest,
  onEvent: (ev: StreamEvent) => void
): Promise<StreamEvent> {
  const res = await fetch(`${BASE}/fetch/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      platform,
      account_id: accountId,
      action: req.action,
      params: req.params,
      async_run: false,
    }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error((data as any).detail || res.statusText);
  }
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let done: StreamEvent | null = null;

  while (true) {
    const { value, done: finished } = await reader.read();
    if (finished) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const chunk = buffer.slice(0, idx).trim();
      buffer = buffer.slice(idx + 2);
      if (!chunk.startsWith('data:')) continue;
      let ev: StreamEvent;
      try {
        ev = JSON.parse(chunk.slice(5).trim());
      } catch {
        continue;
      }
      if (ev.type === 'error') throw new Error(ev.error_message || '抓取失败');
      onEvent(ev);
      if (ev.type === 'done') done = ev;
    }
  }
  return done || { type: 'done', result_count: 0, new_favorites: 0 };
}

// ---------- 定时任务 ----------

export async function listSchedules(): Promise<ScheduleRow[]> {
  const data = await request<{ schedules: ScheduleRow[] }>('/schedules');
  return data.schedules;
}

export async function createSchedule(body: {
  account_id?: string;
  cron_expr: string;
  title?: string;
  action?: string;
  platform?: string;
  params?: Record<string, any>;
}) {
  return request('/schedules', { method: 'POST', body: JSON.stringify(body) });
}

export async function updateSchedule(id: string, body: Record<string, any>) {
  return request(`/schedules/${id}`, { method: 'PATCH', body: JSON.stringify(body) });
}

export async function deleteSchedule(id: string) {
  return request(`/schedules/${id}`, { method: 'DELETE' });
}

export async function triggerSchedule(id: string) {
  return request(`/schedules/${id}/trigger`, { method: 'POST' });
}

// ---------- AI Agent 配置 / 智能打标 ----------

export async function listAgents(): Promise<AgentConfigRow[]> {
  const data = await request<{ agents: AgentConfigRow[] }>('/ai/agents');
  return data.agents;
}

export async function createAgent(body: { name: string; base_url: string; api_key: string; model_id: string }) {
  return request<AgentConfigRow>('/ai/agents', { method: 'POST', body: JSON.stringify(body) });
}

export async function updateAgent(id: string, body: { name?: string; base_url?: string; api_key?: string; model_id?: string }) {
  return request<AgentConfigRow>(`/ai/agents/${id}`, { method: 'PATCH', body: JSON.stringify(body) });
}

export async function deleteAgent(id: string) {
  return request(`/ai/agents/${id}`, { method: 'DELETE' });
}

export interface AgentTestResult {
  ok: boolean;
  latency_ms?: number;
  reply?: string;
  error?: string;
}

/** 连通性测试：后端用该配置发一次最小 chat 请求。 */
export async function testAgent(id: string) {
  return request<AgentTestResult>(`/ai/agents/${id}/test`, { method: 'POST' });
}

// ---------- 标签聚合 ----------

export interface TagStatRow {
  tag: string;
  count: number;
}

export interface TagGroupRow {
  group: string;
  tags: string[];
}

export async function listTags(limit = 100): Promise<{ tags: TagStatRow[]; groups: TagGroupRow[] }> {
  return request(`/tags?limit=${limit}`);
}

// ---------- 收藏批量删除 ----------

/** 批量/单个删除收藏关系，并联动清理不再被引用的内容主表行（contents）。 */
export interface DeleteFavoritesResult {
  deleted: number;
  contents_deleted: number;
}

export async function deleteFavorites(
  items: Array<{ account_id: string; platform: string; content_id: string }>
): Promise<DeleteFavoritesResult> {
  return request('/favorites/batch-delete', { method: 'POST', body: JSON.stringify({ items }) });
}

/** 按账号一键清空本地库全部收藏关系，联动清理孤儿 contents。 */
export async function clearFavorites(accountId: string): Promise<DeleteFavoritesResult> {
  return request(`/favorites?account_id=${encodeURIComponent(accountId)}`, { method: 'DELETE' });
}

/** 重置收藏夹：清空本地库全部账号的收藏关系与 contents（云端不受影响）。 */
export async function clearAllFavorites(): Promise<DeleteFavoritesResult> {
  return request('/favorites', { method: 'DELETE' });
}

// ---------- 标签管理 ----------

export interface TagDeleteResult {
  contents_updated: number;
  favorites_deleted: number;
  contents_deleted: number;
}

/** 删除标签；deleteFavorites=true 时一并删除含该标签的收藏关系。 */
export async function deleteTag(tag: string, deleteFavorites = false): Promise<TagDeleteResult> {
  return request(`/tags/${encodeURIComponent(tag)}?delete_favorites=${deleteFavorites}`, { method: 'DELETE' });
}

export async function tagUsage(tag: string): Promise<{ tag: string; count: number }> {
  return request(`/tags/${encodeURIComponent(tag)}/usage`);
}

export async function createTagGroup(name: string, tags: string[] = []): Promise<TagGroupRow> {
  return request('/tag-groups', { method: 'POST', body: JSON.stringify({ name, tags }) });
}

export async function renameTagGroup(oldName: string, newName: string): Promise<TagGroupRow> {
  return request(`/tag-groups/${encodeURIComponent(oldName)}`, {
    method: 'PUT',
    body: JSON.stringify({ name: newName }),
  });
}

/** 手动打标：整体覆盖某条内容的标签。 */
export async function saveContentTags(contentId: string, tags: string[]) {
  return request<{ content_id: string; tags: string[] }>(`/contents/${encodeURIComponent(contentId)}/tags`, {
    method: 'PUT',
    body: JSON.stringify({ tags }),
  });
}

export interface TagStreamEvent {
  type: 'task' | 'batch' | 'done' | 'error';
  task_id?: string;
  limit?: number;
  processed?: number;
  tagged?: number;
  items?: Array<{ content_id: string; title?: string; tags: string[] }>;
  error_message?: string;
}

/** 一键打标（SSE 流式）：逐批回调进度，结束返回 done 载荷；抛错对应 error 事件。 */
export async function tagStream(
  body: { agent_id: string; platform?: string; limit?: number },
  onEvent: (ev: TagStreamEvent) => void,
  signal?: AbortSignal
): Promise<TagStreamEvent> {
  const res = await fetch(`${BASE}/ai/tag/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      platform: body.platform || '',
      account_id: '',
      action: 'ai_tag',
      params: { agent_id: body.agent_id, platform: body.platform || '', limit: body.limit },
    }),
    signal,
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error((data as any).detail || res.statusText);
  }
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let done: TagStreamEvent | null = null;

  while (true) {
    const { value, done: finished } = await reader.read();
    if (finished) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const chunk = buffer.slice(0, idx).trim();
      buffer = buffer.slice(idx + 2);
      if (!chunk.startsWith('data:')) continue;
      let ev: TagStreamEvent;
      try {
        ev = JSON.parse(chunk.slice(5).trim());
      } catch {
        continue;
      }
      if (ev.type === 'error') throw new Error(ev.error_message || '打标失败');
      onEvent(ev);
      if (ev.type === 'done') done = ev;
    }
  }
  return done || { type: 'done', processed: 0, tagged: 0 };
}

// ---------- 下载队列 ----------

export type DownloaderId = 'yt-dlp' | 'videodl' | 'aria2c';

/** 平台下载清晰度档位（与后端 QUALITY_OPTIONS 一致） */
export const DOWNLOAD_QUALITIES = ['auto', '2160', '1440', '1080', '720', '540', '480'] as const;

export function qualityLabel(q: string): string {
  return q === 'auto' ? 'auto（推荐）' : `${q}p`;
}

export interface DownloadRow {
  download_id: string;
  platform?: PlatformId | null;
  content_id?: string | null;
  account_id?: string | null;
  title?: string | null;
  url: string;
  downloader: DownloaderId;
  quality?: string | null;
  status: 'pending' | 'running' | 'success' | 'failed' | 'canceled' | 'paused';
  progress?: string | null;
  output_path?: string | null;
  error_message?: string | null;
  created_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
}

export async function listDownloads(): Promise<DownloadRow[]> {
  const data = await request<{ downloads: DownloadRow[] }>('/downloads');
  return data.downloads;
}

export async function createDownload(body: {
  content_id: string;
  platform: string;
  account_id?: string;
  title?: string;
  url?: string;
  downloader?: DownloaderId;
  quality?: string;
}): Promise<DownloadRow> {
  return request('/downloads', { method: 'POST', body: JSON.stringify(body) });
}

export async function retryDownload(id: string, downloader?: DownloaderId) {
  return request(`/downloads/${id}/retry`, {
    method: 'POST',
    body: JSON.stringify(downloader ? { downloader } : {}),
  });
}

export async function pauseDownload(id: string) {
  return request(`/downloads/${id}/pause`, { method: 'POST' });
}

/** 在系统文件管理器中打开该任务的输出位置 */
export async function revealDownload(id: string) {
  return request(`/downloads/${id}/reveal`, { method: 'POST' });
}

/** 获取该任务的下载日志（后端每个任务落盘一份 log） */
export async function getDownloadLog(id: string): Promise<{ download_id: string; log: string }> {
  return request(`/downloads/${id}/log`);
}

/** 清空全部下载日志（运行中任务的日志保留），返回删除数量 */
export async function clearDownloadLogs(): Promise<{ deleted: number }> {
  return request('/downloads/logs', { method: 'DELETE' });
}

export async function deleteDownload(id: string) {
  return request(`/downloads/${id}`, { method: 'DELETE' });
}

// ---------- 封面图本地化 ----------

/** 封面统一读取地址：本地已缓存回文件、未缓存由后端 307 跳远程原图（并自动入队本地化）。 */
export function coverApiUrl(platform: string, contentId: string): string {
  return `/api/v1/covers/${encodeURIComponent(platform)}/${encodeURIComponent(contentId)}`;
}

export interface CoverBackfillResult {
  total: number;      // 有封面链接的内容总数
  missing: number;    // 本地缓存缺失数
  reset: number;      // 标记存在但文件丢失、已重置标记数
  enqueued: number;   // 本次提交后台队列数
  queue_size: number;
}

/** 核对封面本地化状态入库，并把缺失封面提交后台队列补齐（防远程链接过期）。 */
export async function backfillCovers(): Promise<CoverBackfillResult> {
  return request('/covers/backfill', { method: 'POST' });
}

export interface CoverStatus {
  total: number;      // 有封面链接的内容总数
  localized: number;  // 已本地化数
  missing: number;    // 缺失数
  queue_size: number; // 队列剩余（含执行中）
}

/** 封面本地化进度（设置页轮询）。 */
export async function fetchCoverStatus(): Promise<CoverStatus> {
  return request('/covers/status');
}

// ---------- 下载工具链检测（yt-dlp / videodl） ----------

export interface ToolchainStatus {
  installed: boolean;
  version: string | null;
}

export function fetchToolchain(): Promise<Record<DownloaderId, ToolchainStatus>> {
  return request('/downloads/toolchain');
}

export type ToolchainUpdateEvent =
  | { type: 'line'; text: string }
  | { type: 'done'; before: string | null; after: string | null; updated: boolean }
  | { type: 'error'; detail: string };

/** 检查更新（未安装时等同安装）：SSE 逐行推送 pip 输出，结束返回 done/error 载荷。 */
export async function updateToolchainStream(
  downloader: DownloaderId,
  onEvent: (ev: ToolchainUpdateEvent) => void,
  signal?: AbortSignal
): Promise<ToolchainUpdateEvent | null> {
  const res = await fetch(`${BASE}/downloads/toolchain/${downloader}/update`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: '{}',
    signal,
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error((data as any).detail || res.statusText);
  }
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let final: ToolchainUpdateEvent | null = null;

  while (true) {
    const { value, done: finished } = await reader.read();
    if (finished) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const chunk = buffer.slice(0, idx).trim();
      buffer = buffer.slice(idx + 2);
      if (!chunk.startsWith('data:')) continue;
      let ev: ToolchainUpdateEvent;
      try {
        ev = JSON.parse(chunk.slice(5).trim());
      } catch {
        continue;
      }
      if (ev.type === 'error') throw new Error(ev.detail || '更新失败');
      onEvent(ev);
      if (ev.type === 'done') final = ev;
    }
  }
  return final;
}

// ---------- 系统设置 / 头像 ----------

export async function uploadAvatar(file: File): Promise<string> {
  // multipart 上传，不能走 request()（它强制 JSON Content-Type）
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${BASE}/settings/avatar`, { method: 'POST', body: form });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((data as any).detail || res.statusText);
  return (data as any).url as string;
}

export async function fetchAvatarUrl(): Promise<string | null> {
  try {
    const res = await fetch(`${BASE}/settings/avatar`);
    // 时间戳参数用于破浏览器缓存
    return res.ok ? `${BASE}/settings/avatar?t=${Date.now()}` : null;
  } catch {
    return null;
  }
}

// ---------- 系统设置 / 运行参数 ----------

export interface AppSettings {
  profile_path: string;
  headless: boolean;
  request_interval: number;
  request_timeout: number;
  download_dir: string;        // 下载根目录，空 = 默认 data/downloads
  download_concurrency: number; // 并发下载数 1-3
  download_category?: string;  // 下载分类目录模板（{platform}/{authorName}…）
  download_quality?: string;   // 平台下载默认清晰度（auto = 平台推荐）
  aria2_rpc_port?: number;     // aria2c RPC 端口
  aria2_connections?: number;  // aria2c 单任务连接分片数
}

export function fetchAppSettings(): Promise<AppSettings> {
  return request('/settings');
}

export function updateAppSettings(patch: Partial<AppSettings>): Promise<AppSettings> {
  return request('/settings', { method: 'PUT', body: JSON.stringify(patch) });
}

// ---------- 通知中心 ----------

export interface NotificationRow {
  notification_id: string;
  type: string;               // info / success / error
  title: string;
  detail?: string | null;
  task_id?: string | null;
  read: number;
  created_at?: string | null;
}

export function listNotifications(limit = 50): Promise<{ notifications: NotificationRow[]; unread: number }> {
  return request(`/notifications?limit=${limit}`);
}

export function markNotificationsRead(): Promise<{ updated: number }> {
  return request('/notifications/read-all', { method: 'POST' });
}
