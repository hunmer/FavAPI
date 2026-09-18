import React, { useState, useEffect, useMemo } from 'react';
import { ScrapedItem, Account } from '../../types';
import { ItemDetailModal } from './ItemDetailModal';
import { ItemActionMenu } from './ItemActionMenu';
import { DownloadConfirmModal } from './DownloadConfirmModal';
import { BrowserFilterPanel } from './BrowserFilterPanel';
import { BrowserToolbar, BrowserSelectionBar } from './BrowserToolbar';
import { BrowserContent } from './BrowserContent';
import { BrowserTagContextMenu, BrowserTagDeleteModal, BrowserGroupCreateModal } from './BrowserTagModals';
import { BrowserItemsDeleteModal, BrowserSingleDeleteModal } from './BrowserDeleteModals';
import { AiTaggingModal } from './AiTaggingModal';
import { useAiTagging } from './useAiTagging';
import * as api from '../../api';
import { useSearchParams } from 'react-router-dom';

/** 过滤条件记忆：离开数据页后再进入，自动恢复上次过滤（localStorage 持久化） */
const FILTERS_STORAGE_KEY = 'favapi_data_filters';

/** 记忆的过滤条件（字段名与 URL 查询参数一致，便于统一读写） */
interface SavedFilters {
  account: string;
  folder: string;
  source: string;
  author: string;
  date: string;
  date_end: string;
  pub_start: string;
  pub_end: string;
  tags: string[];
  q: string;
}

/** 读取记忆的过滤条件；无记忆或 JSON 损坏返回 null（按无记忆处理） */
const readSavedFilters = (): Partial<SavedFilters> | null => {
  try {
    const raw = JSON.parse(localStorage.getItem(FILTERS_STORAGE_KEY) || 'null');
    return raw && typeof raw === 'object' ? raw : null;
  } catch {
    return null;
  }
};

interface DataBrowserViewProps {
  accounts: Account[];
  initialAccountId?: string;
  externalSearchQuery?: string;
  tagStats?: api.TagStatRow[];
  tagGroups?: api.TagGroupRow[];
  agents: api.AgentConfigRow[];
  onTaggingDone: () => void;
  /** 卡片菜单动作结果的轻提示（App 侧全局 toast） */
  showToast?: (message: string, type?: 'success' | 'info' | 'error') => void;
}

/**
 * 数据浏览页：状态与数据逻辑在此组合，界面按功能拆分为子组件
 * （BrowserFilterPanel / BrowserToolbar / BrowserContent / 各弹窗）。
 */
export const DataBrowserView: React.FC<DataBrowserViewProps> = ({
  accounts,
  initialAccountId,
  externalSearchQuery,
  tagStats = [],
  tagGroups = [],
  agents,
  onTaggingDone,
  showToast,
}) => {
  // HashRouter 的查询参数位于 hash 内（/#/data?...），通过路由 hook 读取。
  const [searchParams, setSearchParams] = useSearchParams();

  // View mode with memory (localStorage or fallback to grid)
  const [viewMode, setViewMode] = useState<'grid' | 'list'>(() => {
    const saved = localStorage.getItem('favapi_data_view_mode');
    return saved === 'list' ? 'list' : 'grid';
  });

  const handleViewModeChange = (mode: 'grid' | 'list') => {
    setViewMode(mode);
    localStorage.setItem('favapi_data_view_mode', mode);
  };

  // ---------- 排序（收藏时间 / 时长 + 正反序，localStorage 记忆） ----------
  const [sortBy, setSortBy] = useState<'default' | 'collected' | 'duration'>(() => {
    const saved = localStorage.getItem('favapi_data_sort_by');
    return saved === 'collected' || saved === 'duration' ? saved : 'default';
  });
  const [sortAsc, setSortAsc] = useState(() => localStorage.getItem('favapi_data_sort_order') === 'asc');
  const handleSortByChange = (by: 'default' | 'collected' | 'duration') => {
    setSortBy(by);
    localStorage.setItem('favapi_data_sort_by', by);
  };
  const handleToggleSortOrder = () => {
    setSortAsc((prev) => {
      localStorage.setItem('favapi_data_sort_order', prev ? 'desc' : 'asc');
      return !prev;
    });
  };

  // ---------- 过滤状态（Filter & Search） ----------
  const urlInit = searchParams;
  const savedFilters = readSavedFilters();
  // 恢复优先级：URL 参数（外部跳转显式意图）> localStorage 记忆 > prop/默认
  const initFilter = (urlKey: keyof SavedFilters, fallback = ''): string => {
    if (urlInit.has(urlKey)) return urlInit.get(urlKey) || fallback;
    return (savedFilters?.[urlKey] as string) || fallback;
  };

  const [selectedAccountId, setSelectedAccountId] = useState<string>(
    urlInit.has('account')
      ? urlInit.get('account') || 'all'
      : savedFilters?.account || initialAccountId || 'all'
  );
  const initialQuery = externalSearchQuery || urlInit.get('q') || savedFilters?.q || '';
  const [searchQuery, setSearchQuery] = useState(initialQuery);
  const [selectedFolder, setSelectedFolder] = useState<string>(initFilter('folder', 'all'));
  // 入库来源过滤（收藏列表 / 喜欢列表 / 稍后再看列表…）
  const [selectedSource, setSelectedSource] = useState<string>(initFilter('source', 'all'));
  // 作者过滤器（点击卡片作者名可快捷应用）
  const [selectedAuthor, setSelectedAuthor] = useState<string>(initFilter('author', 'all'));
  // 入库日期 / 发布时间过滤（URL 参数：date、date_end、pub_start、pub_end）
  const [selectedDate, setSelectedDate] = useState<string>(initFilter('date'));
  const [selectedEndDate, setSelectedEndDate] = useState<string>(initFilter('date_end'));
  const handleDateFilterChange = (start: string, end: string) => {
    setSelectedDate(start);
    setSelectedEndDate(end);
  };
  const [selectedPubDate, setSelectedPubDate] = useState<string>(initFilter('pub_start'));
  const [selectedPubEndDate, setSelectedPubEndDate] = useState<string>(initFilter('pub_end'));
  // 多选标签过滤（OR：含任一选中标签即匹配）
  const [selectedTags, setSelectedTags] = useState<string[]>(
    () => urlInit.get('tags')?.split(',').filter(Boolean)
      ?? (Array.isArray(savedFilters?.tags) ? savedFilters.tags : [])
  );

  // 切换账号：账号过滤收敛收藏夹/来源与作者候选，一并重置
  const handleSelectAccount = (id: string) => {
    setSelectedAccountId(id);
    setSelectedFolder('all');
    setSelectedSource('all');
    setSelectedAuthor('all');
  };

  // 切换收藏夹：作者候选按账号+收藏夹收敛，重置作者
  const handleSelectFolder = (folder: string) => {
    setSelectedFolder(folder);
    setSelectedAuthor('all');
  };

  const toggleTag = (tag: string) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
    );
  };

  // 外部全局搜索词变化时同步（挂载时为空则跳过，避免覆盖记忆恢复的搜索词）
  const extSearchPrev = React.useRef(externalSearchQuery);
  useEffect(() => {
    if (extSearchPrev.current !== externalSearchQuery) {
      extSearchPrev.current = externalSearchQuery;
      setSearchQuery(externalSearchQuery);
    }
  }, [externalSearchQuery]);

  // Pagination states: 20, 50, 100, 200
  const [pageSize, setPageSize] = useState<number>(100);
  const [currentPage, setCurrentPage] = useState<number>(1);

  // Selected item modal drawer
  const [activeItemModal, setActiveItemModal] = useState<ScrapedItem | null>(null);

  // ---------- 服务端数据（过滤/分页均由 /favorites 查询执行） ----------
  const [serverItems, setServerItems] = useState<ScrapedItem[]>([]);
  const [totalCount, setTotalCount] = useState(0);   // 当前过滤命中总数（服务端）
  const [listLoading, setListLoading] = useState(false);
  // facets：全库总数 / 各账号计数 / 收藏夹与作者候选
  const [totalAll, setTotalAll] = useState(0);
  const [accountCounts, setAccountCounts] = useState<Map<string, number>>(new Map());
  const [folderFacets, setFolderFacets] = useState<Array<[string, number]>>([]);
  const [sourceFacets, setSourceFacets] = useState<Array<[string, number]>>([]);
  const [authorFacets, setAuthorFacets] = useState<Array<[string, number]>>([]);
  // 打标/删除等数据变更后本地自刷新（叠加 App 侧的 onTaggingDone 全局刷新）
  const [reloadFlag, setReloadFlag] = useState(0);
  const handleRefresh = () => {
    setReloadFlag((v) => v + 1);
    onTaggingDone();
  };

  // ---------- 一键 AI 打标（SSE 流程见 useAiTagging） ----------
  const tagging = useAiTagging({ agents, accounts, selectedAccountId, onDone: handleRefresh });

  // ---------- 标签右键管理 ----------
  const [ctxMenu, setCtxMenu] = useState<{ x: number; y: number; tag: string } | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<{ tag: string; usage: number } | null>(null);
  const [deleteAlsoContents, setDeleteAlsoContents] = useState(false);
  const [tagDeleting, setTagDeleting] = useState(false);

  const openDeleteConfirm = async (tag: string) => {
    setCtxMenu(null);
    try {
      const usage = await api.tagUsage(tag);
      setDeleteConfirm({ tag, usage: usage.count });
    } catch {
      setDeleteConfirm({ tag, usage: -1 });  // 查询失败仍允许删除（文案降级）
    }
    setDeleteAlsoContents(false);
  };

  const confirmDeleteTag = async () => {
    if (!deleteConfirm || tagDeleting) return;
    setTagDeleting(true);
    try {
      await api.deleteTag(deleteConfirm.tag, deleteAlsoContents);
      setSelectedTags((prev) => prev.filter((t) => t !== deleteConfirm.tag));
      setDeleteConfirm(null);
      handleRefresh();  // 刷新列表 / 标签统计 / 分组
    } catch (err: any) {
      alert(`标签删除失败：${err?.message || '未知错误'}`);
    } finally {
      setTagDeleting(false);
    }
  };

  // ---------- 分组管理 ----------
  const [editingGroup, setEditingGroup] = useState<{ group: string; value: string } | null>(null);
  const [groupSaving, setGroupSaving] = useState(false);
  const [showGroupCreate, setShowGroupCreate] = useState(false);
  const [newGroupName, setNewGroupName] = useState('');
  const [newGroupTags, setNewGroupTags] = useState<string[]>([]);

  const submitGroupRename = async () => {
    if (!editingGroup || !editingGroup.value.trim() || groupSaving) return;
    setGroupSaving(true);
    try {
      await api.renameTagGroup(editingGroup.group, editingGroup.value.trim());
      setEditingGroup(null);
      handleRefresh();
    } catch (err: any) {
      alert(`分组重命名失败：${err?.message || '未知错误'}`);
    } finally {
      setGroupSaving(false);
    }
  };

  const submitGroupCreate = async () => {
    if (!newGroupName.trim() || groupSaving) return;
    setGroupSaving(true);
    try {
      await api.createTagGroup(newGroupName.trim(), newGroupTags);
      setShowGroupCreate(false);
      setNewGroupName('');
      setNewGroupTags([]);
      handleRefresh();
    } catch (err: any) {
      alert(`分组创建失败：${err?.message || '未知错误'}`);
    } finally {
      setGroupSaving(false);
    }
  };

  // 手动打标（详情弹窗）：保存后刷新并同步弹窗内数据
  const handleSaveTags = async (tags: string[]) => {
    if (!activeItemModal) return;
    await api.saveContentTags(activeItemModal.id, tags);
    setActiveItemModal({ ...activeItemModal, tags });
    handleRefresh();
  };

  // ---------- 多选与批量删除 ----------
  // favorites 行以 (accountId, platform, id=content_id) 三元组唯一定位
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const [itemsDeleteConfirm, setItemsDeleteConfirm] = useState(false);
  const [itemsDeleting, setItemsDeleting] = useState(false);

  const itemKey = (item: ScrapedItem) => `${item.accountId}|${item.platform}|${item.id}`;

  const toggleSelectItem = (item: ScrapedItem) => {
    const key = itemKey(item);
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const exitSelectionMode = () => {
    setSelectionMode(false);
    setSelectedKeys(new Set());
  };

  // selectedKeys 跨页（全选所有），提交时直接解析 key 还原三元组，不受当前页数据限制
  const confirmDeleteItems = async () => {
    if (selectedKeys.size === 0 || itemsDeleting) return;
    setItemsDeleting(true);
    try {
      const refs = Array.from(selectedKeys).map((key: string) => {
        const [account_id, platform, ...rest] = key.split('|');
        return { account_id, platform, content_id: rest.join('|') };
      });
      await api.deleteFavorites(refs);
      setItemsDeleteConfirm(false);
      exitSelectionMode();
      handleRefresh();  // 刷新列表 / 标签统计 / 分组
    } catch (err: any) {
      alert(`批量删除失败：${err?.message || '未知错误'}`);
    } finally {
      setItemsDeleting(false);
    }
  };

  // ---------- 卡片右键/dots 菜单动作 ----------
  const openExternal = (item: ScrapedItem) => {
    if (!item.url) {
      showToast?.('该条目无链接（刷新页面重新拉取后重试）', 'error');
      return;
    }
    // window.open 被弹窗拦截器拦截时静默返回 null，需明确提示
    if (!window.open(item.url, '_blank', 'noopener,noreferrer')) {
      showToast?.('新窗口被浏览器拦截，请允许本站弹窗后重试（地址栏右侧有拦截图标）', 'error');
    }
  };

  const copyUrl = async (item: ScrapedItem) => {
    if (!item.url) {
      showToast?.('该条目无链接（刷新页面重新拉取后重试）', 'error');
      return;
    }
    try {
      await navigator.clipboard.writeText(item.url);
      showToast?.('已复制链接地址');
    } catch {
      showToast?.('复制失败，请手动复制', 'error');
    }
  };

  /** 账号打开：用该条收藏所属账号的隔离浏览器（session）打开原站链接 */
  const openWithAccount = async (item: ScrapedItem) => {
    if (!item.url) {
      showToast?.('该条目无链接（刷新页面重新拉取后重试）', 'error');
      return;
    }
    try {
      const res = await api.toggleBrowse(item.accountId, item.url);
      showToast?.(
        res.tab
          ? '已在登录/抓取占用的浏览器中新开标签页'
          : res.navigated
            ? '已在打开的账号浏览器中跳转'
            : '已通过账号隔离浏览器打开'
      );
    } catch (err: any) {
      showToast?.(err?.message || '账号浏览器打开失败', 'error');
    }
  };

  /** 下载视频：弹窗选下载器后入队（单条/批量共用），进度在「下载队列」页查看 */
  const [downloadConfirm, setDownloadConfirm] = useState<{ items: ScrapedItem[] } | null>(null);
  const [downloadSubmitting, setDownloadSubmitting] = useState(false);
  // 提供「平台下载」能力的平台集合（决定弹窗是否显示平台下载选项并默认选中）
  const [platformDownloadSet, setPlatformDownloadSet] = useState<Set<string>>(new Set());
  // 默认清晰度（设置页「下载清晰度」，缺省 auto）
  const [defaultQuality, setDefaultQuality] = useState('auto');
  useEffect(() => {
    api.fetchPlatformDownloadSet().then(setPlatformDownloadSet);
    api.fetchAppSettings()
      .then((s) => setDefaultQuality(s.download_quality || 'auto'))
      .catch(() => {});
  }, []);

  const downloadItem = (item: ScrapedItem) => {
    if (!item.url) {
      showToast?.('该条目无链接（刷新页面重新拉取后重试）', 'error');
      return;
    }
    setDownloadConfirm({ items: [item] });
  };

  const confirmDownload = async (downloader: api.DownloaderId, quality: string) => {
    if (!downloadConfirm || downloadSubmitting) return;
    setDownloadSubmitting(true);
    const results = await Promise.allSettled(
      downloadConfirm.items
        .filter((i) => i.url)
        .map((i) =>
          api.createDownload({
            content_id: i.id,
            platform: i.platform,
            account_id: i.accountId || '',
            title: i.title,
            url: i.url,
            downloader,
            quality,
          }),
        ),
    );
    const ok = results.filter((r) => r.status === 'fulfilled').length;
    const failed = results.length - ok;
    setDownloadSubmitting(false);
    setDownloadConfirm(null);
    if (ok) showToast?.(`已加入下载队列 ${ok} 条${failed ? `，失败 ${failed} 条` : ''}`, failed ? 'info' : 'success');
    else showToast?.('加入下载队列失败', 'error');
  };

  /** 批量下载所选（selectedKeys 跨页，从全量 serverItems 还原条目） */
  const downloadSelected = () => {
    const targets = serverItems.filter((i) => selectedKeys.has(itemKey(i)) && i.url);
    if (!targets.length) {
      showToast?.('所选条目均无可下载链接', 'error');
      return;
    }
    setDownloadConfirm({ items: targets });
  };

  // 列表视图行右键菜单
  const [rowMenu, setRowMenu] = useState<{ x: number; y: number; item: ScrapedItem } | null>(null);

  // 单条删除确认（右键菜单【删除】）
  const [singleDelete, setSingleDelete] = useState<ScrapedItem | null>(null);
  const [singleDeleting, setSingleDeleting] = useState(false);
  const confirmDeleteSingle = async () => {
    if (!singleDelete || singleDeleting) return;
    setSingleDeleting(true);
    try {
      await api.deleteFavorites([
        { account_id: singleDelete.accountId, platform: singleDelete.platform, content_id: singleDelete.id },
      ]);
      setSingleDelete(null);
      handleRefresh();
    } catch (err: any) {
      alert(`删除失败：${err?.message || '未知错误'}`);
    } finally {
      setSingleDeleting(false);
    }
  };

  // ---------- 服务端查询 ----------
  // 搜索防抖：输入停顿后再触发查询
  const [debouncedQuery, setDebouncedQuery] = useState(initialQuery);
  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedQuery(searchQuery), 300);
    return () => window.clearTimeout(t);
  }, [searchQuery]);

  // URL 参数与过滤状态双向同步：全部过滤条件入 URL（account/folder/author/date/date_end/pub_start/pub_end/tags/q），
  // 刷新/分享/后退可完整恢复过滤现场。
  const searchParamsString = searchParams.toString();
  const previousSearchParamsStringRef = React.useRef(searchParamsString);
  const urlChangedSincePreviousRender = previousSearchParamsStringRef.current !== searchParamsString;
  useEffect(() => {
    previousSearchParamsStringRef.current = searchParamsString;
    if (!urlChangedSincePreviousRender) return;
    // 浏览器后退/前进或外部跳转（如总览日历卡）时从 URL 回填
    setSelectedAccountId(searchParams.get('account') || 'all');
    setSelectedFolder(searchParams.get('folder') || 'all');
    setSelectedSource(searchParams.get('source') || 'all');
    setSelectedAuthor(searchParams.get('author') || 'all');
    setSelectedDate(searchParams.get('date') || '');
    setSelectedEndDate(searchParams.get('date_end') || '');
    setSelectedPubDate(searchParams.get('pub_start') || '');
    setSelectedPubEndDate(searchParams.get('pub_end') || '');
    setSelectedTags(searchParams.get('tags')?.split(',').filter(Boolean) ?? []);
    setSearchQuery(searchParams.get('q') || '');
  }, [searchParams, searchParamsString, urlChangedSincePreviousRender]);

  // 过滤状态 → URL + localStorage 记忆（replace 不产生历史；q 用防抖值避免每键写 URL）
  useEffect(() => {
    localStorage.setItem(FILTERS_STORAGE_KEY, JSON.stringify({
      account: selectedAccountId,
      folder: selectedFolder,
      source: selectedSource,
      author: selectedAuthor,
      date: selectedDate,
      date_end: selectedEndDate,
      pub_start: selectedPubDate,
      pub_end: selectedPubEndDate,
      tags: selectedTags,
      q: debouncedQuery.trim(),
    }));
    const next = new URLSearchParams();
    if (selectedAccountId !== 'all') next.set('account', selectedAccountId);
    if (selectedFolder !== 'all') next.set('folder', selectedFolder);
    if (selectedSource !== 'all') next.set('source', selectedSource);
    if (selectedAuthor !== 'all') next.set('author', selectedAuthor);
    if (selectedDate) next.set('date', selectedDate);
    if (selectedEndDate) next.set('date_end', selectedEndDate);
    if (selectedPubDate) next.set('pub_start', selectedPubDate);
    if (selectedPubEndDate) next.set('pub_end', selectedPubEndDate);
    if (selectedTags.length) next.set('tags', selectedTags.join(','));
    if (debouncedQuery.trim()) next.set('q', debouncedQuery.trim());
    const nextString = next.toString();
    const currentString = searchParamsString;
    const hasEmptyAccountParam = searchParams.has('account') && !searchParams.get('account');

    // URL 变化触发的状态回填会先经过上一轮渲染；只有状态自身发生变化时才写回，
    // 避免用旧状态覆盖浏览器后退/前进或外部跳转的查询参数。
    if (urlChangedSincePreviousRender) return;

    // 空 account 等价于“全部账号”，统一去掉该参数，避免与有效账号值来回切换。
    if (hasEmptyAccountParam) {
      const normalized = new URLSearchParams(searchParams);
      normalized.delete('account');
      setSearchParams(normalized, { replace: true });
      return;
    }
    if (nextString === currentString) return;
    setSearchParams(next, { replace: true });
  }, [selectedAccountId, selectedFolder, selectedSource, selectedAuthor, selectedDate, selectedEndDate, selectedPubDate, selectedPubEndDate, selectedTags, debouncedQuery, searchParams, searchParamsString, setSearchParams, urlChangedSincePreviousRender]);

  // 当前过滤条件（不含分页）：列表查询与「全选所有」共用，useMemo 保持引用稳定避免请求循环
  const filterOpts = useMemo<api.FavoriteListOpts>(
    () => ({
      accountId: selectedAccountId === 'all' ? undefined : selectedAccountId,
      folder: selectedFolder === 'all' ? undefined : selectedFolder,
      source: selectedSource === 'all' ? undefined : selectedSource,
      author: selectedAuthor === 'all' ? undefined : selectedAuthor,
      dateStart: selectedDate || undefined,
      dateEnd: selectedEndDate || undefined,
      pubStart: selectedPubDate || undefined,
      pubEnd: selectedPubEndDate || undefined,
      tags: selectedTags.length ? selectedTags : undefined,
      q: debouncedQuery.trim() || undefined,
    }),
    [selectedAccountId, selectedFolder, selectedSource, selectedAuthor, selectedDate, selectedEndDate, selectedPubDate, selectedPubEndDate, selectedTags, debouncedQuery]
  );

  // 列表：过滤条件（含分页）变化 → 防抖后向服务端发起查询（连续调整过滤只发最后一次请求）
  useEffect(() => {
    let cancelled = false;
    setListLoading(true);
    const t = window.setTimeout(() => {
      const nameMap = new Map<string, string>(accounts.map((a): [string, string] => [a.id, a.name]));
      api.listFavorites({
        ...filterOpts,
        limit: pageSize,
        offset: (currentPage - 1) * pageSize,
        sortBy: sortBy === 'default' ? undefined : sortBy,
        sortOrder: sortAsc ? 'asc' : 'desc',
      })
        .then(({ total, items }) => {
          if (cancelled) return;
          setTotalCount(total);
          setServerItems(items.map((r) => api.toScrapedItem(r, nameMap)));
        })
        .catch(() => {
          /* 查询失败静默，保留上一次数据 */
        })
        .finally(() => {
          if (!cancelled) setListLoading(false);
        });
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(t);
    };
  }, [filterOpts, currentPage, pageSize, reloadFlag, accounts, sortBy, sortAsc]);

  // facets：收藏夹候选按账号收敛，作者候选按账号+收藏夹收敛
  useEffect(() => {
    let cancelled = false;
    api.favoriteFacets(
      selectedAccountId === 'all' ? undefined : selectedAccountId,
      selectedFolder === 'all' ? undefined : selectedFolder
    )
      .then((f) => {
        if (cancelled) return;
        setTotalAll(f.total);
        setAccountCounts(new Map(f.accounts.map((a) => [a.id, a.count])));
        setFolderFacets(f.folders.map((x) => [x.name, x.count] as [string, number]));
        setSourceFacets((f.sources || []).map((x) => [x.name, x.count] as [string, number]));
        setAuthorFacets(f.authors.map((x) => [x.name, x.count] as [string, number]));
      })
      .catch(() => {
        /* 静默 */
      });
    return () => {
      cancelled = true;
    };
  }, [selectedAccountId, selectedFolder, reloadFlag]);

  // 服务端分页：totalPages 由服务端总数推导
  const totalPages = Math.ceil(totalCount / pageSize) || 1;
  const startIndex = (currentPage - 1) * pageSize;
  const endIndex = Math.min(startIndex + pageSize, totalCount);
  const currentItems = serverItems;

  // 当前页全选 / 取消全选（多选模式）
  const allPageSelected =
    selectionMode && currentItems.length > 0 && currentItems.every((i) => selectedKeys.has(itemKey(i)));
  const toggleSelectAllPage = () => {
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      if (allPageSelected) currentItems.forEach((i) => next.delete(itemKey(i)));
      else currentItems.forEach((i) => next.add(itemKey(i)));
      return next;
    });
  };

  // 全选所有（当前过滤器结果）：分批拉取命中条目的 key 加入选择集；已全选时点击取消全部
  const [selectingAll, setSelectingAll] = useState(false);
  const allFilteredSelected = totalCount > 0 && selectedKeys.size >= totalCount;
  const toggleSelectAllFiltered = async () => {
    if (selectingAll || totalCount === 0) return;
    if (allFilteredSelected) {
      setSelectedKeys(new Set());
      return;
    }
    setSelectingAll(true);
    try {
      const next = new Set(selectedKeys);
      const BATCH = 5000;
      for (let offset = 0; offset < totalCount; offset += BATCH) {
        const { items } = await api.listFavorites({ ...filterOpts, limit: BATCH, offset });
        items.forEach((r) => next.add(`${r.account_id || ''}|${r.platform}|${r.content_id}`));
      }
      setSelectedKeys(next);
    } catch {
      /* 拉取失败保留已选 */
    } finally {
      setSelectingAll(false);
    }
  };

  // Reset page on filter change
  useEffect(() => {
    setCurrentPage(1);
  }, [selectedAccountId, selectedFolder, selectedSource, selectedAuthor, selectedTags, searchQuery, pageSize, selectedDate, selectedEndDate, selectedPubDate, selectedPubEndDate, sortBy, sortAsc]);

  // 服务端总数缩小后当前页越界：回退到最后一页
  useEffect(() => {
    if (currentPage > totalPages) setCurrentPage(totalPages);
  }, [totalPages]);

  // 是否有任一过滤器激活（底部“清空全部过滤”按钮的显示条件）
  const hasActiveFilters =
    searchQuery.trim() !== '' ||
    selectedAccountId !== 'all' ||
    selectedFolder !== 'all' ||
    selectedSource !== 'all' ||
    selectedAuthor !== 'all' ||
    selectedDate !== '' ||
    selectedEndDate !== '' ||
    selectedPubDate !== '' ||
    selectedPubEndDate !== '' ||
    selectedTags.length > 0;

  const clearAllFilters = () => {
    setSearchQuery('');
    setSelectedAccountId('all');
    setSelectedFolder('all');
    setSelectedSource('all');
    setSelectedAuthor('all');
    setSelectedTags([]);
    setSelectedPubDate('');
    setSelectedPubEndDate('');
    handleDateFilterChange('', '');  // 同步清除 URL ?date= / ?date_end=
  };

  // 翻页：桌面回滚内部列表到顶，移动端回到视图顶部（sticky 标题行之下）
  const gotoPage = (page: number) => {
    const next = Math.min(Math.max(1, page), totalPages);
    if (next === currentPage) return;
    setCurrentPage(next);
    document.getElementById('data-browser-scroll')?.scrollTo({ top: 0, behavior: 'smooth' });
    document.getElementById('data-browser-view')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <div id="data-browser-view" className="flex flex-col lg:flex-row gap-6 items-start">
      {/* 左：过滤面板 */}
      <BrowserFilterPanel
        accounts={accounts}
        accountCounts={accountCounts}
        totalAll={totalAll}
        totalCount={totalCount}
        selectedAccountId={selectedAccountId}
        onSelectAccount={handleSelectAccount}
        searchQuery={searchQuery}
        onSearchQueryChange={setSearchQuery}
        folderFacets={folderFacets}
        selectedFolder={selectedFolder}
        onSelectFolder={handleSelectFolder}
        sourceFacets={sourceFacets}
        selectedSource={selectedSource}
        onSelectSource={setSelectedSource}
        authorFacets={authorFacets}
        selectedAuthor={selectedAuthor}
        onSelectAuthor={setSelectedAuthor}
        selectedDate={selectedDate}
        selectedEndDate={selectedEndDate}
        onDateRangeChange={handleDateFilterChange}
        selectedPubDate={selectedPubDate}
        selectedPubEndDate={selectedPubEndDate}
        onPubStartChange={setSelectedPubDate}
        onPubEndChange={setSelectedPubEndDate}
        tagStats={tagStats}
        tagGroups={tagGroups}
        selectedTags={selectedTags}
        onToggleTag={toggleTag}
        onClearTags={() => setSelectedTags([])}
        onTagContextMenu={(x, y, tag) => setCtxMenu({ x, y, tag })}
        editingGroup={editingGroup}
        onEditingGroupChange={setEditingGroup}
        groupSaving={groupSaving}
        onSubmitGroupRename={submitGroupRename}
        onOpenGroupCreate={() => {
          setNewGroupName('');
          setNewGroupTags([]);
          setShowGroupCreate(true);
        }}
        hasActiveFilters={hasActiveFilters}
        onClearAllFilters={clearAllFilters}
      />

      {/* 右：内容区（桌面端固定填满可用高度，列表内部滚动，翻页钉底） */}
      <div className="flex-1 min-w-0 w-full flex flex-col gap-6 lg:h-[calc(96vh-7rem)]">
        <BrowserToolbar
          listLoading={listLoading}
          viewMode={viewMode}
          onViewModeChange={handleViewModeChange}
          selectionMode={selectionMode}
          onEnterSelectionMode={() => setSelectionMode(true)}
          onExitSelectionMode={exitSelectionMode}
          totalCount={totalCount}
          selectedCount={selectedKeys.size}
          agentsAvailable={agents.length > 0}
          onOpenTagModal={tagging.openTagModal}
          sortBy={sortBy}
          onSortByChange={handleSortByChange}
          sortAsc={sortAsc}
          onToggleSortOrder={handleToggleSortOrder}
        />

        {/* 多选模式批量操作条：全选当前页 / 删除 */}
        {selectionMode && totalCount > 0 && (
          <BrowserSelectionBar
            selectedCount={selectedKeys.size}
            totalCount={totalCount}
            selectingAll={selectingAll}
            allFilteredSelected={allFilteredSelected}
            onToggleSelectAllFiltered={toggleSelectAllFiltered}
            allPageSelected={allPageSelected}
            onToggleSelectAllPage={toggleSelectAllPage}
            onDownloadSelected={downloadSelected}
            onDeleteSelected={() => setItemsDeleteConfirm(true)}
          />
        )}

        {/* Content Rendering: Empty state / Grid View / List View + Pagination（内部滚动区） */}
        <BrowserContent
          listLoading={listLoading}
          totalCount={totalCount}
          totalAll={totalAll}
          viewMode={viewMode}
          currentItems={currentItems}
          selectionMode={selectionMode}
          selectedKeys={selectedKeys}
          itemKey={itemKey}
          onToggleSelectItem={toggleSelectItem}
          allPageSelected={allPageSelected}
          onToggleSelectAllPage={toggleSelectAllPage}
          onOpenItem={setActiveItemModal}
          onFilterAuthor={(author) =>
            setSelectedAuthor((prev) => (prev === author ? 'all' : author))
          }
          onOpenExternal={openExternal}
          onCopyUrl={copyUrl}
          onOpenWithAccount={openWithAccount}
          onDownload={downloadItem}
          onDeleteItem={setSingleDelete}
          onRowContextMenu={(x, y, item) => setRowMenu({ x, y, item })}
          startIndex={startIndex}
          endIndex={endIndex}
          pageSize={pageSize}
          onPageSizeChange={setPageSize}
          currentPage={currentPage}
          totalPages={totalPages}
          onGotoPage={gotoPage}
        />
      </div>{/* /右：内容区 */}

      {/* Item Detail Drawer Modal */}
      {activeItemModal && (
        <ItemDetailModal
          item={activeItemModal}
          onClose={() => setActiveItemModal(null)}
          onSaveTags={handleSaveTags}
        />
      )}

      {/* 列表视图行右键菜单（与卡片菜单同款） */}
      {rowMenu && (
        <ItemActionMenu
          item={rowMenu.item}
          x={rowMenu.x}
          y={rowMenu.y}
          onClose={() => setRowMenu(null)}
          onOpenExternal={openExternal}
          onCopyUrl={copyUrl}
          onOpenWithAccount={openWithAccount}
          onDownload={downloadItem}
          onDelete={setSingleDelete}
        />
      )}

      {/* 下载确认弹窗（单条右键菜单 / 批量工具栏共用） */}
      {downloadConfirm && (
        <DownloadConfirmModal
          count={downloadConfirm.items.length}
          singleTitle={downloadConfirm.items.length === 1 ? downloadConfirm.items[0].title : undefined}
          platformDownload={
            downloadConfirm.items.length > 0 &&
            downloadConfirm.items.every((i) => platformDownloadSet.has(i.platform))
          }
          defaultQuality={defaultQuality}
          confirming={downloadSubmitting}
          onConfirm={confirmDownload}
          onClose={() => !downloadSubmitting && setDownloadConfirm(null)}
        />
      )}

      {/* 标签右键菜单 */}
      {ctxMenu && (
        <BrowserTagContextMenu
          ctxMenu={ctxMenu}
          onClose={() => setCtxMenu(null)}
          onDeleteTag={openDeleteConfirm}
        />
      )}

      {/* 删除标签确认（AlertDialog + checkbox，默认不勾选） */}
      {deleteConfirm && (
        <BrowserTagDeleteModal
          confirm={deleteConfirm}
          alsoContents={deleteAlsoContents}
          onAlsoContentsChange={setDeleteAlsoContents}
          deleting={tagDeleting}
          onClose={() => setDeleteConfirm(null)}
          onConfirm={confirmDeleteTag}
        />
      )}

      {/* 批量删除收藏确认（多选模式） */}
      {itemsDeleteConfirm && (
        <BrowserItemsDeleteModal
          count={selectedKeys.size}
          deleting={itemsDeleting}
          onClose={() => setItemsDeleteConfirm(false)}
          onConfirm={confirmDeleteItems}
        />
      )}

      {/* 单条删除收藏确认（卡片右键菜单【删除】） */}
      {singleDelete && (
        <BrowserSingleDeleteModal
          item={singleDelete}
          deleting={singleDeleting}
          onClose={() => setSingleDelete(null)}
          onConfirm={confirmDeleteSingle}
        />
      )}

      {/* 新建分组弹窗（可选归入「其他」组标签） */}
      {showGroupCreate && (
        <BrowserGroupCreateModal
          groups={tagGroups}
          name={newGroupName}
          onNameChange={setNewGroupName}
          pickedTags={newGroupTags}
          onTogglePickedTag={(t) =>
            setNewGroupTags((prev) => (prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t]))
          }
          saving={groupSaving}
          onClose={() => setShowGroupCreate(false)}
          onSubmit={submitGroupCreate}
        />
      )}

      {/* One-shot AI Tagging Modal */}
      {tagging.showTagModal && (
        <AiTaggingModal
          agents={agents}
          agentId={tagging.tagAgentId}
          onAgentIdChange={tagging.setTagAgentId}
          platform={tagging.tagPlatform}
          onPlatformChange={tagging.setTagPlatform}
          limit={tagging.tagLimit}
          onLimitChange={tagging.setTagLimit}
          starting={tagging.tagStarting}
          phase={tagging.tagPhase}
          result={tagging.tagResult}
          progress={tagging.tagProgress}
          listRef={tagging.tagListRef}
          onClose={() => tagging.setShowTagModal(false)}
          onStart={tagging.startTagging}
          onStop={tagging.stopTagging}
          onRetry={() => {
            tagging.setTagPhase('idle');
            tagging.setTagResult(null);
          }}
        />
      )}
    </div>
  );
};
