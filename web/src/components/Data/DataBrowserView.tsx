import React, { useState, useEffect, useMemo } from 'react';
import { ScrapedItem, Account } from '../../types';
import { PLATFORMS } from '../../data/mockFavData';
import {
  Database,
  LayoutGrid,
  List,
  Search,
  Bookmark,
  Clock,
  CalendarDays,
  User,
  Filter,
  ChevronLeft,
  ChevronRight,
  Folder,
  Tag,
  Share2,
  Sparkles,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  X,
  Plus,
  Pencil,
  Trash2,
  CheckSquare,
  ChevronDown,
} from 'lucide-react';
import { ItemDetailModal } from './ItemDetailModal';
import { DataItemCard } from './DataItemCard';
import { ItemActionMenu } from './ItemActionMenu';
import { SiteIcon } from '../SiteIcon';
import * as api from '../../api';
import { useDismiss } from '../../hooks/useDismiss';
import { useSearchParams } from 'react-router-dom';

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

/** 过滤状态初始化：读取当前地址栏查询参数（组件外使用，不依赖 hooks）。 */
const searchParamsInit = () => new URLSearchParams(window.location.search);

/** 过滤器标题行右侧的清空小图标按钮 */
const FilterClearBtn: React.FC<{ onClick: () => void; title: string }> = ({ onClick, title }) => (
  <button
    type="button"
    onClick={onClick}
    title={title}
    className="w-5 h-5 rounded-full bg-slate-100 hover:bg-rose-100 text-slate-400 hover:text-rose-500 flex items-center justify-center transition-colors cursor-pointer shrink-0"
  >
    <X className="w-3 h-3" />
  </button>
);

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
  // View mode with memory (localStorage or fallback to grid)
  const [viewMode, setViewMode] = useState<'grid' | 'list'>(() => {
    const saved = localStorage.getItem('favapi_data_view_mode');
    return saved === 'list' ? 'list' : 'grid';
  });

  const handleViewModeChange = (mode: 'grid' | 'list') => {
    setViewMode(mode);
    localStorage.setItem('favapi_data_view_mode', mode);
  };

  // Filter & Search states
  const [selectedAccountId, setSelectedAccountId] = useState<string>(
    searchParamsInit().get('account') || initialAccountId || 'all'
  );
  // 账号选择器（自定义折叠列表：原生 select 的 option 无法嵌入平台图标）
  const [accountListOpen, setAccountListOpen] = useState(false);
  const selectedAccount = accounts.find((a) => a.id === selectedAccountId);
  // 收藏夹选择器同款交互
  const [folderListOpen, setFolderListOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState(externalSearchQuery || searchParamsInit().get('q') || '');
  const [selectedFolder, setSelectedFolder] = useState<string>(searchParamsInit().get('folder') || 'all');
  // 作者过滤器（点击卡片作者名可快捷应用）
  const [selectedAuthor, setSelectedAuthor] = useState<string>(searchParamsInit().get('author') || 'all');
  const [authorListOpen, setAuthorListOpen] = useState(false);
  // 入库日期 / 发布时间过滤（URL 参数：date、date_end、pub_start、pub_end）
  const [selectedDate, setSelectedDate] = useState<string>(searchParamsInit().get('date') || '');
  const [selectedEndDate, setSelectedEndDate] = useState<string>(searchParamsInit().get('date_end') || '');
  const handleDateFilterChange = (start: string, end: string) => {
    setSelectedDate(start);
    setSelectedEndDate(end);
  };
  const [selectedPubDate, setSelectedPubDate] = useState<string>(searchParamsInit().get('pub_start') || '');
  const [selectedPubEndDate, setSelectedPubEndDate] = useState<string>(searchParamsInit().get('pub_end') || '');
  // 多选标签过滤（OR：含任一选中标签即匹配）
  const [selectedTags, setSelectedTags] = useState<string[]>(
    () => searchParamsInit().get('tags')?.split(',').filter(Boolean) ?? []
  );
  // 标签分组折叠状态（默认全部展开）
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({});

  // ---------- 服务端数据（过滤/分页均由 /favorites 查询执行） ----------
  const [serverItems, setServerItems] = useState<ScrapedItem[]>([]);
  const [totalCount, setTotalCount] = useState(0);   // 当前过滤命中总数（服务端）
  const [listLoading, setListLoading] = useState(false);
  // facets：全库总数 / 各账号计数 / 收藏夹与作者候选
  const [totalAll, setTotalAll] = useState(0);
  const [accountCounts, setAccountCounts] = useState<Map<string, number>>(new Map());
  const [folderFacets, setFolderFacets] = useState<Array<[string, number]>>([]);
  const [authorFacets, setAuthorFacets] = useState<Array<[string, number]>>([]);
  // 打标/删除等数据变更后本地自刷新（叠加 App 侧的 onTaggingDone 全局刷新）
  const [reloadFlag, setReloadFlag] = useState(0);
  const handleRefresh = () => {
    setReloadFlag((v) => v + 1);
    onTaggingDone();
  };

  // ---------- 标签右键管理 ----------
  const [ctxMenu, setCtxMenu] = useState<{ x: number; y: number; tag: string } | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<{ tag: string; usage: number } | null>(null);
  const [deleteAlsoContents, setDeleteAlsoContents] = useState(false);
  const [tagDeleting, setTagDeleting] = useState(false);

  // 点击任意处关闭右键菜单
  useDismiss(() => setCtxMenu(null), !!ctxMenu);

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

  const toggleTag = (tag: string) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
    );
  };

  useEffect(() => {
    if (externalSearchQuery !== undefined) {
      setSearchQuery(externalSearchQuery);
    }
  }, [externalSearchQuery]);

  // Pagination states: 20, 50, 100, 200
  const [pageSize, setPageSize] = useState<number>(100);
  const [currentPage, setCurrentPage] = useState<number>(1);

  // Selected item modal drawer
  const [activeItemModal, setActiveItemModal] = useState<ScrapedItem | null>(null);

  // ---------- 一键 AI 打标 ----------
  const [showTagModal, setShowTagModal] = useState(false);
  const [tagAgentId, setTagAgentId] = useState('');
  const [tagPlatform, setTagPlatform] = useState('');
  const [tagLimit, setTagLimit] = useState(50);
  const [tagStarting, setTagStarting] = useState(false);
  // idle=表单 / running=任务执行中 / success / failed
  const [tagPhase, setTagPhase] = useState<'idle' | 'running' | 'success' | 'failed'>('idle');
  const [tagResult, setTagResult] = useState<{ processed: number; tagged: number; error?: string; taskId?: string } | null>(null);
  // SSE 实时进度：每批打标结果流式追加
  const [tagProgress, setTagProgress] = useState<{ processed: number; tagged: number; limit: number; results: Array<{ title: string; tags: string[] }> }>({ processed: 0, tagged: 0, limit: 0, results: [] });
  const tagAbortRef = React.useRef<AbortController | null>(null);
  // 同步最新进度到 ref，供停止/异常回调读取（避免闭包陈旧值）
  const tagProgressRef = React.useRef(tagProgress);
  tagProgressRef.current = tagProgress;
  const tagListRef = React.useRef<HTMLDivElement>(null);

  useEffect(() => {
    tagListRef.current?.scrollTo({ top: tagListRef.current.scrollHeight });
  }, [tagProgress.results.length]);

  const openTagModal = () => {
    // 预选当前筛选账号所属平台（未选具体账号则全部）
    setTagAgentId(agents[0]?.agent_id || '');
    setTagPlatform(accounts.find((a) => a.id === selectedAccountId)?.platform || '');
    setTagLimit(50);
    setTagPhase('idle');
    setTagResult(null);
    setTagProgress({ processed: 0, tagged: 0, limit: 0, results: [] });
    setShowTagModal(true);
  };

  const appendBatch = (batch: api.TagStreamEvent) => {
    setTagProgress((prev) => ({
      processed: batch.processed ?? prev.processed,
      tagged: batch.tagged ?? prev.tagged,
      limit: batch.limit ?? prev.limit,
      results: [...prev.results, ...(batch.items || []).map((it) => ({ title: it.title || it.content_id, tags: it.tags }))],
    }));
  };

  const startTagging = async () => {
    if (!tagAgentId) return;
    setTagStarting(true);
    const abort = new AbortController();
    tagAbortRef.current = abort;
    try {
      const done = await api.tagStream(
        { agent_id: tagAgentId, platform: tagPlatform, limit: tagLimit },
        (ev) => {
          if (ev.type === 'task') {
            setTagPhase('running');
            setTagResult({ processed: 0, tagged: 0, taskId: ev.task_id });
            setTagProgress({ processed: 0, tagged: 0, limit: ev.limit ?? tagLimit, results: [] });
          } else if (ev.type === 'batch') {
            appendBatch(ev);
          }
        },
        abort.signal
      );
      setTagPhase('success');
      setTagResult({ processed: done.processed ?? 0, tagged: done.tagged ?? 0, taskId: done.task_id });
      handleRefresh();  // 刷新收藏列表与标签统计
    } catch (err: any) {
      // 用户主动中止：已推流的批次结果保留在进度里
      if (abort.signal.aborted) {
        const latest = tagProgressRef.current;
        setTagPhase('failed');
        setTagResult({ processed: latest.processed, tagged: latest.tagged, error: '已手动停止（已完成批次保留）' });
        handleRefresh();
      } else {
        setTagPhase('failed');
        setTagResult({ processed: 0, tagged: 0, error: err?.message || '任务发起失败' });
      }
    } finally {
      setTagStarting(false);
      tagAbortRef.current = null;
    }
  };

  const stopTagging = () => tagAbortRef.current?.abort();

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
      const refs = Array.from(selectedKeys).map((key) => {
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
    if (!item.url) return;
    window.open(item.url, '_blank', 'noopener,noreferrer');
  };

  const copyUrl = async (item: ScrapedItem) => {
    if (!item.url) return;
    try {
      await navigator.clipboard.writeText(item.url);
      showToast?.('已复制链接地址');
    } catch {
      showToast?.('复制失败，请手动复制', 'error');
    }
  };

  /** 账号打开：用该条收藏所属账号的隔离浏览器（session）打开原站链接 */
  const openWithAccount = async (item: ScrapedItem) => {
    if (!item.url) return;
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
  const [debouncedQuery, setDebouncedQuery] = useState(externalSearchQuery || '');
  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedQuery(searchQuery), 300);
    return () => window.clearTimeout(t);
  }, [searchQuery]);

  // URL 参数与过滤状态双向同步：全部过滤条件入 URL（account/folder/author/date/date_end/pub_start/pub_end/tags/q），
  // 刷新/分享/后退可完整恢复过滤现场。
  const [searchParams, setSearchParams] = useSearchParams();
  const firstRenderRef = React.useRef(true);
  useEffect(() => {
    if (firstRenderRef.current) {
      firstRenderRef.current = false;
      return;
    }
    // 浏览器后退/前进或外部跳转（如总览日历卡）时从 URL 回填
    setSelectedAccountId(searchParams.get('account') || 'all');
    setSelectedFolder(searchParams.get('folder') || 'all');
    setSelectedAuthor(searchParams.get('author') || 'all');
    setSelectedDate(searchParams.get('date') || '');
    setSelectedEndDate(searchParams.get('date_end') || '');
    setSelectedPubDate(searchParams.get('pub_start') || '');
    setSelectedPubEndDate(searchParams.get('pub_end') || '');
    setSelectedTags(searchParams.get('tags')?.split(',').filter(Boolean) ?? []);
    setSearchQuery(searchParams.get('q') || '');
  }, [searchParams]);

  // 过滤状态 → URL（replace 不产生历史；q 用防抖值避免每键写 URL）
  useEffect(() => {
    const next = new URLSearchParams();
    if (selectedAccountId !== 'all') next.set('account', selectedAccountId);
    if (selectedFolder !== 'all') next.set('folder', selectedFolder);
    if (selectedAuthor !== 'all') next.set('author', selectedAuthor);
    if (selectedDate) next.set('date', selectedDate);
    if (selectedEndDate) next.set('date_end', selectedEndDate);
    if (selectedPubDate) next.set('pub_start', selectedPubDate);
    if (selectedPubEndDate) next.set('pub_end', selectedPubEndDate);
    if (selectedTags.length) next.set('tags', selectedTags.join(','));
    if (debouncedQuery.trim()) next.set('q', debouncedQuery.trim());
    if (next.toString() === searchParams.toString()) return;
    setSearchParams(next, { replace: true });
  }, [selectedAccountId, selectedFolder, selectedAuthor, selectedDate, selectedEndDate, selectedPubDate, selectedPubEndDate, selectedTags, debouncedQuery, searchParams, setSearchParams]);

  // 当前过滤条件（不含分页）：列表查询与「全选所有」共用，useMemo 保持引用稳定避免请求循环
  const filterOpts = useMemo<api.FavoriteListOpts>(
    () => ({
      accountId: selectedAccountId === 'all' ? undefined : selectedAccountId,
      folder: selectedFolder === 'all' ? undefined : selectedFolder,
      author: selectedAuthor === 'all' ? undefined : selectedAuthor,
      dateStart: selectedDate || undefined,
      dateEnd: selectedEndDate || undefined,
      pubStart: selectedPubDate || undefined,
      pubEnd: selectedPubEndDate || undefined,
      tags: selectedTags.length ? selectedTags : undefined,
      q: debouncedQuery.trim() || undefined,
    }),
    [selectedAccountId, selectedFolder, selectedAuthor, selectedDate, selectedEndDate, selectedPubDate, selectedPubEndDate, selectedTags, debouncedQuery]
  );

  // 列表：过滤条件（含分页）变化 → 防抖后向服务端发起查询（连续调整过滤只发最后一次请求）
  useEffect(() => {
    let cancelled = false;
    setListLoading(true);
    const t = window.setTimeout(() => {
      const nameMap = new Map(accounts.map((a) => [a.id, a.name]));
      api.listFavorites({
        ...filterOpts,
        limit: pageSize,
        offset: (currentPage - 1) * pageSize,
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
  }, [filterOpts, currentPage, pageSize, reloadFlag, accounts]);

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
  }, [selectedAccountId, selectedFolder, selectedAuthor, selectedTags, searchQuery, pageSize, selectedDate, selectedEndDate, selectedPubDate, selectedPubEndDate]);

  // 服务端总数缩小后当前页越界：回退到最后一页
  useEffect(() => {
    if (currentPage > totalPages) setCurrentPage(totalPages);
  }, [totalPages]);

  // 是否有任一过滤器激活（底部“清空全部过滤”按钮的显示条件）
  const hasActiveFilters =
    searchQuery.trim() !== '' ||
    selectedAccountId !== 'all' ||
    selectedFolder !== 'all' ||
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
      <aside className="w-full lg:w-60 xl:w-64 shrink-0 lg:self-stretch">
        <div className="lg:sticky lg:top-4 lg:max-h-[calc(96vh-7rem)] bg-white rounded-3xl border border-slate-200/80 shadow-2xs flex flex-col overflow-hidden">
          <div className="lg:overflow-y-auto p-4 flex flex-col gap-4">
          {/* Search */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="搜索标题、UP主、标签..."
              className={`w-full pl-8 ${searchQuery ? 'pr-8' : 'pr-3'} py-2 rounded-xl border border-slate-200 text-xs focus:outline-none focus:ring-2 focus:ring-slate-900 bg-slate-50/50`}
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 w-5 h-5 rounded-full bg-slate-200 hover:bg-slate-300 text-slate-500 hover:text-slate-700 flex items-center justify-center transition-colors cursor-pointer"
                title="清空搜索"
              >
                <X className="w-3 h-3" />
              </button>
            )}
          </div>

          {/* Account selector */}
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-slate-600 uppercase tracking-wider">账号</span>
              {selectedAccountId !== 'all' && (
                <FilterClearBtn
                  title="清除账号过滤"
                  onClick={() => {
                    setSelectedAccountId('all');
                    setSelectedFolder('all');
                    setSelectedAuthor('all');
                  }}
                />
              )}
            </div>
            <div className="rounded-xl border border-slate-200 bg-slate-50 overflow-hidden">
              <button
                type="button"
                onClick={() => setAccountListOpen((v) => !v)}
                className="w-full px-3 py-2 flex items-center justify-between gap-2 text-xs font-medium text-slate-800 cursor-pointer hover:bg-slate-100 transition-colors"
              >
                <span className="flex items-center gap-1.5 min-w-0">
                  {selectedAccount ? (
                    <SiteIcon platform={selectedAccount.platform} name={selectedAccount.name} className="w-3.5 h-3.5" />
                  ) : (
                    <User className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                  )}
                  <span className="truncate">
                    {selectedAccount
                      ? `${selectedAccount.name} (${accountCounts.get(selectedAccount.id) ?? 0})`
                      : `全部账号 (${totalAll})`}
                  </span>
                </span>
                <ChevronDown
                  className={`w-3.5 h-3.5 text-slate-400 shrink-0 transition-transform ${accountListOpen ? 'rotate-180' : ''}`}
                />
              </button>
              {accountListOpen && (
                <div className="border-t border-slate-100 max-h-52 overflow-y-auto bg-white">
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedAccountId('all');
                      setSelectedFolder('all');
                      setSelectedAuthor('all');
                      setAccountListOpen(false);
                    }}
                    className={`w-full px-3 py-2 flex items-center gap-1.5 text-xs cursor-pointer transition-colors ${
                      selectedAccountId === 'all'
                        ? 'bg-violet-50 text-violet-700 font-semibold'
                        : 'text-slate-600 hover:bg-slate-50'
                    }`}
                  >
                    <User className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                    <span className="truncate">全部账号 ({totalAll})</span>
                  </button>
                  {accounts.map((acc) => (
                      <button
                        key={acc.id}
                        type="button"
                        onClick={() => {
                          setSelectedAccountId(acc.id);
                          setSelectedFolder('all');
                          setSelectedAuthor('all');
                          setAccountListOpen(false);
                        }}
                        className={`w-full px-3 py-2 flex items-center gap-1.5 text-xs cursor-pointer transition-colors ${
                          selectedAccountId === acc.id
                            ? 'bg-violet-50 text-violet-700 font-semibold'
                            : 'text-slate-600 hover:bg-slate-50'
                        }`}
                      >
                        <SiteIcon platform={acc.platform} name={acc.name} className="w-3.5 h-3.5" />
                        <span className="truncate">
                          {acc.name} ({accountCounts.get(acc.id) ?? 0})
                        </span>
                      </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Folder selector（与账号选择器同款折叠列表） */}
          {folderFacets.length > 0 && (
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-600 uppercase tracking-wider">收藏夹</span>
                {selectedFolder !== 'all' && (
                  <FilterClearBtn
                    title="清除收藏夹过滤"
                    onClick={() => {
                      setSelectedFolder('all');
                      setSelectedAuthor('all');
                    }}
                  />
                )}
              </div>
              <div className="rounded-xl border border-slate-200 bg-slate-50 overflow-hidden">
                <button
                  type="button"
                  onClick={() => setFolderListOpen((v) => !v)}
                  className="w-full px-3 py-2 flex items-center justify-between gap-2 text-xs font-medium text-slate-800 cursor-pointer hover:bg-slate-100 transition-colors"
                >
                  <span className="flex items-center gap-1.5 min-w-0">
                    <Folder
                      className={`w-3.5 h-3.5 shrink-0 ${selectedFolder === 'all' ? 'text-slate-400' : 'text-amber-500'}`}
                    />
                    <span className="truncate">
                      {selectedFolder === 'all' ? '全部收藏夹' : selectedFolder}
                    </span>
                  </span>
                  <ChevronDown
                    className={`w-3.5 h-3.5 text-slate-400 shrink-0 transition-transform ${folderListOpen ? 'rotate-180' : ''}`}
                  />
                </button>
                {folderListOpen && (
                  <div className="border-t border-slate-100 max-h-52 overflow-y-auto bg-white">
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedFolder('all');
                        setSelectedAuthor('all');
                        setFolderListOpen(false);
                      }}
                      className={`w-full px-3 py-2 flex items-center gap-1.5 text-xs cursor-pointer transition-colors ${
                        selectedFolder === 'all'
                          ? 'bg-violet-50 text-violet-700 font-semibold'
                          : 'text-slate-600 hover:bg-slate-50'
                      }`}
                    >
                      <Folder className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                      <span className="truncate">全部收藏夹</span>
                    </button>
                    {folderFacets.map(([name, count]) => (
                      <button
                        key={name}
                        type="button"
                        onClick={() => {
                          setSelectedFolder(name);
                          setSelectedAuthor('all');
                          setFolderListOpen(false);
                        }}
                        className={`w-full px-3 py-2 flex items-center gap-1.5 text-xs cursor-pointer transition-colors ${
                          selectedFolder === name
                            ? 'bg-violet-50 text-violet-700 font-semibold'
                            : 'text-slate-600 hover:bg-slate-50'
                        }`}
                      >
                        <Folder className="w-3.5 h-3.5 text-amber-500 shrink-0" />
                        <span className="truncate">
                          {name} ({count})
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Author selector（与收藏夹选择器同款交互，点击卡片作者名可快捷应用） */}
          {authorFacets.length > 0 && (
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-600 uppercase tracking-wider">作者 / UP主</span>
                {selectedAuthor !== 'all' && (
                  <FilterClearBtn title="清除作者过滤" onClick={() => setSelectedAuthor('all')} />
                )}
              </div>
              <div className="rounded-xl border border-slate-200 bg-slate-50 overflow-hidden">
                <button
                  type="button"
                  onClick={() => setAuthorListOpen((v) => !v)}
                  className="w-full px-3 py-2 flex items-center justify-between gap-2 text-xs font-medium text-slate-800 cursor-pointer hover:bg-slate-100 transition-colors"
                >
                  <span className="flex items-center gap-1.5 min-w-0">
                    <User
                      className={`w-3.5 h-3.5 shrink-0 ${selectedAuthor === 'all' ? 'text-slate-400' : 'text-violet-500'}`}
                    />
                    <span className="truncate">
                      {selectedAuthor === 'all' ? '全部作者' : selectedAuthor}
                    </span>
                  </span>
                  <ChevronDown
                    className={`w-3.5 h-3.5 text-slate-400 shrink-0 transition-transform ${authorListOpen ? 'rotate-180' : ''}`}
                  />
                </button>
                {authorListOpen && (
                  <div className="border-t border-slate-100 max-h-52 overflow-y-auto bg-white">
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedAuthor('all');
                        setAuthorListOpen(false);
                      }}
                      className={`w-full px-3 py-2 flex items-center gap-1.5 text-xs cursor-pointer transition-colors ${
                        selectedAuthor === 'all'
                          ? 'bg-violet-50 text-violet-700 font-semibold'
                          : 'text-slate-600 hover:bg-slate-50'
                      }`}
                    >
                      <User className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                      <span className="truncate">全部作者</span>
                    </button>
                    {authorFacets.map(([author, count]) => (
                      <button
                        key={author}
                        type="button"
                        onClick={() => {
                          setSelectedAuthor(author);
                          setAuthorListOpen(false);
                        }}
                        className={`w-full px-3 py-2 flex items-center gap-1.5 text-xs cursor-pointer transition-colors ${
                          selectedAuthor === author
                            ? 'bg-violet-50 text-violet-700 font-semibold'
                            : 'text-slate-600 hover:bg-slate-50'
                        }`}
                      >
                        <User className="w-3.5 h-3.5 text-violet-400 shrink-0" />
                        <span className="truncate">
                          {author} ({count})
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Crawl date filter（按抓取入库时间过滤） */}
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-slate-600 uppercase tracking-wider flex items-center gap-1.5">
                <Clock className="w-3 h-3 text-sky-500" />
                入库日期
              </span>
              {(selectedDate || selectedEndDate) && (
                <FilterClearBtn title="清除日期过滤" onClick={() => handleDateFilterChange('', '')} />
              )}
            </div>
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] text-slate-400 w-5 shrink-0 text-center">起</span>
                <input
                  type="date"
                  value={selectedDate}
                  max={selectedEndDate || undefined}
                  onChange={(e) => handleDateFilterChange(e.target.value, selectedEndDate)}
                  className="flex-1 min-w-0 px-2 py-2 rounded-xl border border-slate-200 text-xs bg-slate-50 text-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-900 font-medium cursor-pointer"
                />
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] text-slate-400 w-5 shrink-0 text-center">止</span>
                <input
                  type="date"
                  value={selectedEndDate}
                  min={selectedDate || undefined}
                  onChange={(e) => handleDateFilterChange(selectedDate, e.target.value)}
                  className="flex-1 min-w-0 px-2 py-2 rounded-xl border border-slate-200 text-xs bg-slate-50 text-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-900 font-medium cursor-pointer"
                />
              </div>
            </div>
            <p className="text-[10px] text-slate-400">
              按抓取入库时间过滤，可只填一端；总览日历卡可一键跳转带入。
            </p>
          </div>

          {/* Publish date filter（按作品发布时间过滤，取自内容元数据） */}
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-slate-600 uppercase tracking-wider flex items-center gap-1.5">
                <CalendarDays className="w-3 h-3 text-emerald-500" />
                发布时间
              </span>
              {(selectedPubDate || selectedPubEndDate) && (
                <FilterClearBtn
                  title="清除发布时间过滤"
                  onClick={() => {
                    setSelectedPubDate('');
                    setSelectedPubEndDate('');
                  }}
                />
              )}
            </div>
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] text-slate-400 w-5 shrink-0 text-center">起</span>
                <input
                  type="date"
                  value={selectedPubDate}
                  max={selectedPubEndDate || undefined}
                  onChange={(e) => setSelectedPubDate(e.target.value)}
                  className="flex-1 min-w-0 px-2 py-2 rounded-xl border border-slate-200 text-xs bg-slate-50 text-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-900 font-medium cursor-pointer"
                />
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] text-slate-400 w-5 shrink-0 text-center">止</span>
                <input
                  type="date"
                  value={selectedPubEndDate}
                  min={selectedPubDate || undefined}
                  onChange={(e) => setSelectedPubEndDate(e.target.value)}
                  className="flex-1 min-w-0 px-2 py-2 rounded-xl border border-slate-200 text-xs bg-slate-50 text-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-900 font-medium cursor-pointer"
                />
              </div>
            </div>
            <p className="text-[10px] text-slate-400">
              按作品在源平台的发布时间过滤；小红书等无发布时间数据的内容会被排除。
            </p>
          </div>

          {/* AI 标签：按体系分组展示，badge 多选（OR）*/}
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-slate-600 uppercase tracking-wider flex items-center gap-1.5">
                <Tag className="w-3 h-3 text-violet-500" />
                AI 标签
              </span>
              <div className="flex items-center gap-2.5">
                {selectedTags.length > 0 && (
                  <FilterClearBtn
                    title={`清除标签过滤（已选 ${selectedTags.length} 个）`}
                    onClick={() => setSelectedTags([])}
                  />
                )}
                <button
                  type="button"
                  onClick={() => {
                    setNewGroupName('');
                    setNewGroupTags([]);
                    setShowGroupCreate(true);
                  }}
                  className="w-6 h-6 rounded-lg bg-violet-50 border border-violet-100 text-violet-500 hover:bg-violet-100 hover:text-violet-600 flex items-center justify-center transition-all active:scale-95 cursor-pointer"
                  title="新建标签分组"
                >
                  <Plus className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
            {(() => {
              const countByTag = new Map(tagStats.map((t) => [t.tag, t.count]));
              return (
                <div className="flex flex-col gap-2.5 max-h-96 overflow-y-auto pr-0.5">
                  {tagGroups.map((g) => {
                    const groupSelected = g.tags.filter((t) => selectedTags.includes(t)).length;
                    const collapsed = collapsedGroups[g.group];
                    const isEditing = editingGroup?.group === g.group;
                    const isOther = g.group === '其他';
                    return (
                      <div key={g.group}>
                        {isEditing ? (
                          /* 组名行内编辑 */
                          <div className="flex items-center gap-1 py-0.5">
                            <input
                              autoFocus
                              type="text"
                              value={editingGroup.value}
                              onChange={(e) => setEditingGroup({ group: g.group, value: e.target.value })}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') submitGroupRename();
                                if (e.key === 'Escape') setEditingGroup(null);
                              }}
                              className="flex-1 min-w-0 px-2 py-1 rounded-lg border border-violet-300 text-[11px] font-bold text-slate-700 focus:outline-none focus:ring-2 focus:ring-violet-500"
                            />
                            <button
                              type="button"
                              onClick={submitGroupRename}
                              disabled={groupSaving}
                              className="p-1 rounded-md text-emerald-600 hover:bg-emerald-50 disabled:opacity-50 cursor-pointer"
                              title="保存"
                            >
                              <CheckCircle2 className="w-3.5 h-3.5" />
                            </button>
                            <button
                              type="button"
                              onClick={() => setEditingGroup(null)}
                              className="p-1 rounded-md text-slate-400 hover:bg-slate-100 cursor-pointer"
                              title="取消"
                            >
                              <X className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        ) : (
                          <div className="w-full flex items-center justify-between py-0.5 group/head">
                            <button
                              type="button"
                              onClick={() => setCollapsedGroups((prev) => ({ ...prev, [g.group]: !collapsed }))}
                              className="flex items-center gap-1 text-[11px] font-bold text-slate-500 hover:text-slate-800 transition-colors cursor-pointer"
                            >
                              {g.group}
                              {groupSelected > 0 && (
                                <span className="px-1.5 rounded-full bg-violet-600 text-white text-[9px] leading-4">
                                  {groupSelected}
                                </span>
                              )}
                            </button>
                            <div className="flex items-center gap-0.5">
                              {!isOther && (
                                <button
                                  type="button"
                                  onClick={() => setEditingGroup({ group: g.group, value: g.group })}
                                  className="p-0.5 rounded text-slate-300 hover:text-slate-600 opacity-0 group-hover/head:opacity-100 transition-all cursor-pointer"
                                  title="重命名分组"
                                >
                                  <Pencil className="w-3 h-3" />
                                </button>
                              )}
                              <button
                                type="button"
                                onClick={() => setCollapsedGroups((prev) => ({ ...prev, [g.group]: !collapsed }))}
                                className="p-0.5 text-slate-400 cursor-pointer"
                              >
                                <ChevronRight
                                  className={`w-3 h-3 transition-transform ${collapsed ? '' : 'rotate-90'}`}
                                />
                              </button>
                            </div>
                          </div>
                        )}
                        {!collapsed && (
                          <div className="flex flex-wrap gap-1.5 mt-1.5">
                            {g.tags.map((t) => {
                              const active = selectedTags.includes(t);
                              const count = countByTag.get(t);
                              return (
                                <button
                                  key={t}
                                  type="button"
                                  onClick={() => toggleTag(t)}
                                  onContextMenu={(e) => {
                                    e.preventDefault();
                                    e.stopPropagation();
                                    setCtxMenu({ x: e.clientX, y: e.clientY, tag: t });
                                  }}
                                  title="左键筛选 · 右键管理"
                                  className={`px-2 py-1 rounded-lg text-[11px] font-medium border transition-all cursor-pointer active:scale-95 ${
                                    active
                                      ? 'bg-violet-600 text-white border-violet-600 shadow-xs'
                                      : count
                                        ? 'bg-violet-50/60 text-violet-600 border-violet-100 hover:bg-violet-100 hover:border-violet-200'
                                        : 'bg-slate-50 text-slate-400 border-slate-100 hover:border-slate-200 hover:text-slate-500'
                                  }`}
                                >
                                  #{t}
                                  {count ? (
                                    <span className={`ml-1 text-[10px] ${active ? 'text-white/70' : 'text-violet-400'}`}>
                                      {count}
                                    </span>
                                  ) : null}
                                </button>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              );
            })()}
          </div>

          {/* 筛选统计小结 */}
          <div className="pt-3 border-t border-slate-100 text-[11px] text-slate-400">
            命中 <strong className="text-slate-700">{totalCount}</strong> / {totalAll} 条
            {(selectedDate || selectedEndDate) && (
              <span>（入库 {selectedDate || '…'} ~ {selectedEndDate || '…'}）</span>
            )}
            {(selectedPubDate || selectedPubEndDate) && (
              <span>（发布 {selectedPubDate || '…'} ~ {selectedPubEndDate || '…'}）</span>
            )}
            {selectedAuthor !== 'all' && <span>（作者：{selectedAuthor}）</span>}
            {selectedTags.length > 0 && <span>（含任一选中标签）</span>}
          </div>
          </div>

          {/* 清空全部过滤（面板底部固定，不随过滤项滚动） */}
          {totalAll > 0 && hasActiveFilters && (
            <div className="p-3 border-t border-slate-100">
              <button
                type="button"
                onClick={clearAllFilters}
                className="w-full px-4 py-2 rounded-xl border border-slate-200 hover:border-rose-200 hover:bg-rose-50 text-slate-500 hover:text-rose-600 text-xs font-bold shadow-2xs inline-flex items-center justify-center gap-1.5 transition-all active:scale-95 cursor-pointer"
              >
                <X className="w-3.5 h-3.5" />
                清空全部过滤
              </button>
            </div>
          )}
        </div>
      </aside>

      {/* 右：内容区（桌面端固定填满可用高度，列表内部滚动，翻页钉底） */}
      <div className="flex-1 min-w-0 w-full flex flex-col gap-6 lg:h-[calc(96vh-7rem)]">
      {/* Header with Title & View Mode Switcher（移动端页面滚动时吸顶） */}
      <div className="sticky top-0 z-20 bg-[#F8FAFC] dark:bg-[#0D1117] flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900 flex items-center gap-2">
            数据浏览
            {listLoading && <Loader2 className="w-4 h-4 text-violet-500 animate-spin" />}
          </h2>
        </div>

        {/* View mode toggle: List vs Grid + 一键打标 + 多选 */}
        <div className="flex items-center gap-2.5 self-start sm:self-auto">
          {selectionMode ? (
            <button
              type="button"
              onClick={exitSelectionMode}
              className="px-4 py-2 rounded-2xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold shadow-sm inline-flex items-center gap-1.5 transition-all active:scale-95 cursor-pointer"
            >
              <X className="w-3.5 h-3.5" />
              退出多选
            </button>
          ) : (
            <button
              type="button"
              onClick={() => setSelectionMode(true)}
              disabled={totalCount === 0}
              className="px-4 py-2 rounded-2xl bg-white hover:bg-slate-100 disabled:opacity-50 disabled:cursor-not-allowed border border-slate-200 text-slate-700 text-xs font-bold shadow-sm inline-flex items-center gap-1.5 transition-all active:scale-95 cursor-pointer"
              title="进入多选模式，可勾选多条收藏批量删除"
            >
              <CheckSquare className="w-3.5 h-3.5" />
              多选
            </button>
          )}
          <button
            type="button"
            onClick={openTagModal}
            disabled={agents.length === 0}
            className="px-4 py-2 rounded-2xl bg-violet-600 hover:bg-violet-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-bold shadow-sm inline-flex items-center gap-1.5 transition-all active:scale-95 cursor-pointer"
            title={agents.length === 0 ? '请先在设置页创建 AI Agent 配置' : '对未打标的收藏内容执行一次性 AI 打标'}
          >
            <Sparkles className="w-3.5 h-3.5" />
            一键打标
          </button>
          <div className="bg-slate-100 p-1 rounded-2xl border border-slate-200 flex items-center gap-1 shadow-2xs">
            <button
              type="button"
              onClick={() => handleViewModeChange('grid')}
              className={`px-3 py-1.5 rounded-xl text-xs font-semibold flex items-center gap-1.5 transition-all ${
                viewMode === 'grid'
                  ? 'bg-white text-slate-900 shadow-xs'
                  : 'text-slate-500 hover:text-slate-800'
              }`}
              title="网格视图：封面卡片流，适合快速找内容"
            >
              <LayoutGrid className="w-3.5 h-3.5" />
              <span>网格视图</span>
            </button>
            <button
              type="button"
              onClick={() => handleViewModeChange('list')}
              className={`px-3 py-1.5 rounded-xl text-xs font-semibold flex items-center gap-1.5 transition-all ${
                viewMode === 'list'
                  ? 'bg-white text-slate-900 shadow-xs'
                  : 'text-slate-500 hover:text-slate-800'
              }`}
              title="列表视图：逐条信息核对，展现点赞/收藏与时间明细"
            >
              <List className="w-3.5 h-3.5" />
              <span>列表视图</span>
            </button>
          </div>
        </div>
      </div>

      {/* 多选模式批量操作条：全选当前页 / 删除 */}
      {selectionMode && totalCount > 0 && (
        <div className="bg-white p-3 rounded-2xl border border-violet-200/80 shadow-2xs flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
          <span className="font-semibold text-slate-700">
            已选 <strong className="text-violet-600">{selectedKeys.size}</strong> 条收藏
            <span className="ml-2 text-[11px] text-slate-400 font-normal">点击卡片勾选，再次点击取消</span>
          </span>
          <div className="flex items-center gap-2 self-end sm:self-auto">
            <button
              type="button"
              onClick={toggleSelectAllFiltered}
              disabled={selectingAll}
              title="选中当前过滤器命中的全部条目（跨页），再次点击取消全部"
              className="px-3.5 py-2 rounded-xl border border-slate-200 hover:bg-slate-100 disabled:opacity-50 disabled:cursor-wait text-slate-700 font-semibold inline-flex items-center gap-1.5 transition-all active:scale-95 cursor-pointer"
            >
              {selectingAll ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <CheckSquare className="w-3.5 h-3.5" />
              )}
              {selectingAll
                ? '选取中...'
                : allFilteredSelected
                  ? `取消全部 (${totalCount})`
                  : `全选所有 (${totalCount})`}
            </button>
            <button
              type="button"
              onClick={toggleSelectAllPage}
              className="px-3.5 py-2 rounded-xl border border-slate-200 hover:bg-slate-100 text-slate-700 font-semibold inline-flex items-center gap-1.5 transition-all active:scale-95 cursor-pointer"
            >
              <CheckSquare className="w-3.5 h-3.5" />
              {allPageSelected ? '取消本页全选' : '全选本页'}
            </button>
            <button
              type="button"
              onClick={() => setItemsDeleteConfirm(true)}
              disabled={selectedKeys.size === 0}
              className="px-3.5 py-2 rounded-xl bg-rose-600 hover:bg-rose-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-bold inline-flex items-center gap-1.5 transition-all active:scale-95 cursor-pointer"
            >
              <Trash2 className="w-3.5 h-3.5" />
              删除所选
            </button>
          </div>
        </div>
      )}

      {/* Content Rendering: Empty state / Grid View / List View（内部滚动区） */}
      <div
        id="data-browser-scroll"
        className={`flex-1 min-h-0 overflow-y-auto pb-20 lg:pb-0 transition-opacity ${listLoading ? 'opacity-50' : ''}`}
      >
      {totalCount === 0 ? (
        /* 空数据占位：区分全库为空与筛选无命中 */
        <div className="bg-white rounded-[28px] border border-dashed border-slate-200 py-20 flex flex-col items-center justify-center gap-3 text-center">
          <div className="w-14 h-14 rounded-3xl bg-slate-50 text-slate-300 flex items-center justify-center">
            <Database className="w-7 h-7" />
          </div>
          <div className="text-sm font-bold text-slate-500">
            {totalAll === 0 ? '收藏库还是空的' : '没有符合条件的收藏'}
          </div>
          <p className="text-xs text-slate-400 max-w-xs leading-relaxed">
            {totalAll === 0
              ? '先到「账号管理」对平台账号执行一次抓取，数据入库后即可在这里浏览与打标。'
              : '试试调整左侧的账号、收藏夹、标签或搜索关键词。'}
          </p>
        </div>
      ) : viewMode === 'grid' ? (
        /* Grid View: Cover card stream with video metrics overlay */
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 sm:gap-5">
          {currentItems.map((item, idx) => (
            <DataItemCard
              key={item.id}
              item={item}
              idx={idx}
              onSelect={setActiveItemModal}
              selectable={selectionMode}
              selected={selectedKeys.has(itemKey(item))}
              onToggleSelect={toggleSelectItem}
              onFilterAuthor={(author) =>
                setSelectedAuthor((prev) => (prev === author ? 'all' : author))
              }
              onOpenExternal={openExternal}
              onCopyUrl={copyUrl}
              onOpenWithAccount={openWithAccount}
              onDelete={setSingleDelete}
            />
          ))}
        </div>
      ) : (
        /* List View: Detailed row inspection */
        <div className="bg-white rounded-[28px] border border-slate-200/80 shadow-2xs overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-slate-50/80 text-slate-500 border-b border-slate-200 font-semibold">
                  {selectionMode && (
                    <th className="py-3 px-4 w-10">
                      <input
                        type="checkbox"
                        checked={allPageSelected}
                        onChange={toggleSelectAllPage}
                        className="w-4 h-4 rounded accent-violet-600 cursor-pointer"
                        title="全选/取消本页"
                      />
                    </th>
                  )}
                  <th className="py-3 px-4 w-16">封面</th>
                  <th className="py-3 px-4">标题 (点击跳转原站)</th>
                  <th className="py-3 px-4">作者 / UP主</th>
                  <th className="py-3 px-4">时长</th>
                  <th className="py-3 px-4 text-right">点赞 / 收藏</th>
                  <th className="py-3 px-4">所属收藏夹</th>
                  <th className="py-3 px-4">收藏时间</th>
                  <th className="py-3 px-4">抓取入库时间</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {currentItems.map((item, idx) => {
                  const rowSelected = selectionMode && selectedKeys.has(itemKey(item));
                  return (
                  <tr
                    key={item.id}
                    onClick={() => (selectionMode ? toggleSelectItem(item) : setActiveItemModal(item))}
                    onContextMenu={(e) => {
                      e.preventDefault();
                      setRowMenu({ x: e.clientX, y: e.clientY, item });
                    }}
                    className={`anim-row-enter cursor-pointer transition-colors ${
                      rowSelected ? 'bg-violet-50/70' : 'hover:bg-slate-50/80'
                    }`}
                    style={{ animationDelay: `${Math.min(idx * 20, 200)}ms` }}
                  >
                    {selectionMode && (
                      <td className="py-2.5 px-4" onClick={(e) => e.stopPropagation()}>
                        <input
                          type="checkbox"
                          checked={rowSelected}
                          onChange={() => toggleSelectItem(item)}
                          className="w-4 h-4 rounded accent-violet-600 cursor-pointer"
                        />
                      </td>
                    )}
                    <td className="py-2.5 px-4">
                      <img
                        src={item.coverUrl}
                        alt=""
                        className="w-14 h-9 rounded-lg object-cover bg-slate-200 shrink-0"
                        referrerPolicy="no-referrer"
                      />
                    </td>
                    <td className="py-2.5 px-4 max-w-sm">
                      <a
                        href={item.url}
                        target="_blank"
                        rel="noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="font-bold text-slate-900 hover:text-indigo-600 line-clamp-2"
                      >
                        {item.title}
                      </a>
                      {item.tags && item.tags.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1">
                          {item.tags.slice(0, 4).map((t) => (
                            <span
                              key={t}
                              className="px-1.5 py-0.5 rounded bg-violet-50 text-violet-600 text-[10px] font-medium border border-violet-100"
                            >
                              #{t}
                            </span>
                          ))}
                        </div>
                      )}
                      <div className="text-[10px] text-slate-400 mt-0.5 flex items-center gap-1.5">
                        <span>{item.accountName}</span>
                      </div>
                    </td>
                    <td className="py-2.5 px-4 font-medium text-slate-800 whitespace-nowrap">
                      {item.author}
                    </td>
                    <td className="py-2.5 px-4 font-mono text-slate-600 whitespace-nowrap">
                      {item.duration || '—'}
                    </td>
                    <td className="py-2.5 px-4 text-right whitespace-nowrap font-medium text-slate-700">
                      <div>{(item.likes / 1000).toFixed(1)}k 赞</div>
                      <div className="text-[10px] text-slate-400">{(item.favorites / 1000).toFixed(1)}k 藏</div>
                    </td>
                    <td className="py-2.5 px-4 whitespace-nowrap">
                      <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-700 font-medium">
                        {item.folderName}
                      </span>
                    </td>
                    <td className="py-2.5 px-4 text-slate-500 whitespace-nowrap">
                      {item.favTime}
                    </td>
                    <td className="py-2.5 px-4 text-slate-400 text-[11px] whitespace-nowrap">
                      {item.crawlTime}
                    </td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
      </div>

      {/* Pagination Footer（无数据时隐藏；sticky 于 main 滚动视口底部，卡片圆角样式，不脱离容器） */}
      {totalCount > 0 && (
      <div className="sticky bottom-4 z-20 bg-white p-4 rounded-2xl border border-slate-200/80 shadow-lg flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs text-slate-600">
        <div className="flex items-center gap-3">
          <span>
            显示第 <strong className="text-slate-900">{startIndex + 1}</strong> 到{' '}
            <strong className="text-slate-900">{endIndex}</strong> 条，共{' '}
            <strong className="text-slate-900">{totalCount}</strong> 条已入库收藏
          </span>

          <div className="flex items-center gap-1">
            <span className="text-slate-400">每页:</span>
            <select
              value={pageSize}
              onChange={(e) => setPageSize(Number(e.target.value))}
              className="px-2 py-1 rounded-lg border border-slate-200 bg-slate-50 text-slate-700 font-semibold"
            >
              <option value="20">20 条</option>
              <option value="50">50 条</option>
              <option value="100">100 条</option>
              <option value="200">200 条</option>
            </select>
          </div>
        </div>

        {/* Page controls */}
        <div className="flex items-center gap-1.5 self-end sm:self-auto">
          <button
            type="button"
            disabled={currentPage <= 1}
            onClick={() => gotoPage(currentPage - 1)}
            className="p-1.5 rounded-xl border border-slate-200 bg-white hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed shadow-2xs"
            title="上一页"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <span className="px-3 py-1 font-semibold text-slate-800">
            {currentPage} / {totalPages}
          </span>
          <button
            type="button"
            disabled={currentPage >= totalPages}
            onClick={() => gotoPage(currentPage + 1)}
            className="p-1.5 rounded-xl border border-slate-200 bg-white hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed shadow-2xs"
            title="下一页"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>
      )}
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
          onDelete={setSingleDelete}
        />
      )}

      {/* 标签右键菜单 */}
      {ctxMenu && (
        <div
          className="fixed z-[60] py-1 rounded-xl bg-white border border-slate-200 shadow-lg overflow-hidden anim-modal-enter"
          style={{ left: Math.min(ctxMenu.x, window.innerWidth - 140), top: ctxMenu.y }}
          onClick={(e) => e.stopPropagation()}
        >
          <button
            type="button"
            onClick={() => openDeleteConfirm(ctxMenu.tag)}
            className="w-full px-3.5 py-2 text-left text-xs font-semibold text-rose-600 hover:bg-rose-50 flex items-center gap-2 cursor-pointer"
          >
            <Trash2 className="w-3.5 h-3.5" />
            删除标签「{ctxMenu.tag}」
          </button>
        </div>
      )}

      {/* 删除标签确认（AlertDialog + checkbox，默认不勾选） */}
      {deleteConfirm && (
        <div
          className="fixed inset-0 z-[70] bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 anim-backdrop-enter"
          onClick={() => !tagDeleting && setDeleteConfirm(null)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="anim-modal-enter bg-white w-full max-w-sm rounded-[28px] p-6 shadow-2xl border border-slate-100 space-y-4"
          >
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-2xl bg-rose-50 text-rose-600 flex items-center justify-center shrink-0">
                <AlertTriangle className="w-5 h-5" />
              </div>
              <h3 className="text-base font-bold text-slate-900">删除标签</h3>
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">
              将从
              {deleteConfirm.usage >= 0 ? (
                <>
                  <strong className="text-slate-900">{deleteConfirm.usage}</strong> 条内容中
                </>
              ) : ''}{' '}
              移除标签 <span className="font-bold text-violet-600">#{deleteConfirm.tag}</span>
              （含各分组内的该标签）。
            </p>
            <label className="flex items-start gap-2.5 p-3 rounded-2xl bg-rose-50/60 border border-rose-100 cursor-pointer">
              <input
                type="checkbox"
                checked={deleteAlsoContents}
                onChange={(e) => setDeleteAlsoContents(e.target.checked)}
                className="mt-0.5 w-4 h-4 rounded accent-rose-600 cursor-pointer"
              />
              <span className="text-xs text-slate-700">
                <strong className="text-rose-600">一并删除这些收藏内容</strong>
                <span className="block text-[11px] text-slate-400 mt-0.5">
                  含该标签的收藏将全部从收藏库移除（不可恢复），内容元数据保留
                </span>
              </span>
            </label>
            <div className="flex justify-end gap-2 pt-1">
              <button
                type="button"
                onClick={() => setDeleteConfirm(null)}
                disabled={tagDeleting}
                className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-800 rounded-xl cursor-pointer"
              >
                取消
              </button>
              <button
                type="button"
                onClick={confirmDeleteTag}
                disabled={tagDeleting}
                className="px-4 py-2 bg-rose-600 hover:bg-rose-700 disabled:opacity-50 text-white text-xs font-bold rounded-xl flex items-center gap-1.5 cursor-pointer"
              >
                <Trash2 className="w-3.5 h-3.5" />
                {tagDeleting ? '删除中...' : deleteAlsoContents ? '删除标签与收藏' : '删除标签'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 批量删除收藏确认（多选模式） */}
      {itemsDeleteConfirm && (
        <div
          className="fixed inset-0 z-[70] bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 anim-backdrop-enter"
          onClick={() => !itemsDeleting && setItemsDeleteConfirm(false)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="anim-modal-enter bg-white w-full max-w-sm rounded-[28px] p-6 shadow-2xl border border-slate-100 space-y-4"
          >
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-2xl bg-rose-50 text-rose-600 flex items-center justify-center shrink-0">
                <AlertTriangle className="w-5 h-5" />
              </div>
              <h3 className="text-base font-bold text-slate-900">批量删除收藏</h3>
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">
              确定删除已选中的{' '}
              <strong className="text-rose-600">{selectedKeys.size}</strong> 条收藏吗？
              删除后将从收藏列表移除（不可恢复），内容元数据保留。
            </p>
            <div className="flex justify-end gap-2 pt-1">
              <button
                type="button"
                onClick={() => setItemsDeleteConfirm(false)}
                disabled={itemsDeleting}
                className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-800 rounded-xl cursor-pointer"
              >
                取消
              </button>
              <button
                type="button"
                onClick={confirmDeleteItems}
                disabled={itemsDeleting}
                className="px-4 py-2 bg-rose-600 hover:bg-rose-700 disabled:opacity-50 text-white text-xs font-bold rounded-xl flex items-center gap-1.5 cursor-pointer"
              >
                <Trash2 className="w-3.5 h-3.5" />
                {itemsDeleting ? '删除中...' : '确认删除'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 单条删除收藏确认（卡片右键菜单【删除】） */}
      {singleDelete && (
        <div
          className="fixed inset-0 z-[70] bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 anim-backdrop-enter"
          onClick={() => !singleDeleting && setSingleDelete(null)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="anim-modal-enter bg-white w-full max-w-sm rounded-[28px] p-6 shadow-2xl border border-slate-100 space-y-4"
          >
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-2xl bg-rose-50 text-rose-600 flex items-center justify-center shrink-0">
                <AlertTriangle className="w-5 h-5" />
              </div>
              <h3 className="text-base font-bold text-slate-900">删除收藏</h3>
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">
              确定删除收藏「
              <strong className="text-slate-900 break-all line-clamp-2">{singleDelete.title}</strong>
              」吗？删除后将从收藏列表移除（不可恢复），内容元数据保留。
            </p>
            <div className="flex justify-end gap-2 pt-1">
              <button
                type="button"
                onClick={() => setSingleDelete(null)}
                disabled={singleDeleting}
                className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-800 rounded-xl cursor-pointer"
              >
                取消
              </button>
              <button
                type="button"
                onClick={confirmDeleteSingle}
                disabled={singleDeleting}
                className="px-4 py-2 bg-rose-600 hover:bg-rose-700 disabled:opacity-50 text-white text-xs font-bold rounded-xl flex items-center gap-1.5 cursor-pointer"
              >
                <Trash2 className="w-3.5 h-3.5" />
                {singleDeleting ? '删除中...' : '确认删除'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 新建分组弹窗（可选归入「其他」组标签） */}
      {showGroupCreate && (
        <div
          className="fixed inset-0 z-[70] bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 anim-backdrop-enter"
          onClick={() => !groupSaving && setShowGroupCreate(false)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="anim-modal-enter bg-white w-full max-w-sm rounded-[28px] shadow-2xl border border-slate-100 overflow-hidden"
          >
            <div className="p-5 bg-slate-50 border-b border-slate-100">
              <h3 className="text-base font-bold text-slate-900">新建标签分组</h3>
              <p className="text-xs text-slate-500 mt-0.5">
                创建后可在分组内积累标签，打标标签池同步生效
              </p>
            </div>
            <div className="p-5 space-y-4">
              <input
                autoFocus
                type="text"
                value={newGroupName}
                onChange={(e) => setNewGroupName(e.target.value)}
                placeholder="分组名称，如：兴趣爱好"
                className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-violet-600"
              />
              {(() => {
                const otherGroup = tagGroups.find((g) => g.group === '其他');
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
                    <span className="text-xs font-bold text-slate-600 block mb-2">
                      归入「其他」组的标签（可选）
                    </span>
                    <div className="flex flex-wrap gap-1.5 max-h-40 overflow-y-auto p-1">
                      {otherTags.map((t) => {
                        const on = newGroupTags.includes(t);
                        return (
                          <button
                            key={t}
                            type="button"
                            onClick={() =>
                              setNewGroupTags((prev) =>
                                on ? prev.filter((x) => x !== t) : [...prev, t]
                              )
                            }
                            className={`px-2 py-1 rounded-lg text-[11px] font-medium border transition-all cursor-pointer active:scale-95 ${
                              on
                                ? 'bg-violet-600 text-white border-violet-600'
                                : 'bg-violet-50/60 text-violet-600 border-violet-100 hover:bg-violet-100'
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
                  onClick={() => setShowGroupCreate(false)}
                  disabled={groupSaving}
                  className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-800 rounded-xl cursor-pointer"
                >
                  取消
                </button>
                <button
                  type="button"
                  onClick={submitGroupCreate}
                  disabled={groupSaving || !newGroupName.trim()}
                  className="px-4 py-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white text-xs font-bold rounded-xl flex items-center gap-1.5 cursor-pointer"
                >
                  <Plus className="w-3.5 h-3.5" />
                  {groupSaving ? '创建中...' : '创建分组'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* One-shot AI Tagging Modal */}
      {showTagModal && (
        <div
          className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 anim-backdrop-enter"
          onClick={() => tagPhase !== 'running' && setShowTagModal(false)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="anim-modal-enter bg-white w-full max-w-md rounded-[28px] shadow-2xl border border-slate-100 overflow-hidden"
          >
            <div className="p-5 bg-slate-50 border-b border-slate-100 flex items-center justify-between">
              <div>
                <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-violet-600" />
                  一键 AI 智能打标
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  对尚未打标的收藏内容执行一次性批量打标
                </p>
              </div>
              {tagPhase !== 'running' && (
                <button
                  type="button"
                  onClick={() => setShowTagModal(false)}
                  className="w-8 h-8 rounded-full bg-white hover:bg-slate-200 text-slate-700 flex items-center justify-center shadow-2xs cursor-pointer"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>

            <div className="p-6 space-y-5">
              {tagPhase === 'idle' ? (
                <>
                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1.5 uppercase tracking-wider">
                      AI Agent 配置 <span className="text-red-500">*</span>
                    </label>
                    <select
                      value={tagAgentId}
                      onChange={(e) => setTagAgentId(e.target.value)}
                      className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-violet-600"
                    >
                      {agents.map((a) => (
                        <option key={a.agent_id} value={a.agent_id}>
                          {a.name}（{a.model_id}）
                        </option>
                      ))}
                    </select>
                    <p className="text-[11px] text-slate-400 mt-1">
                      可在「设置 → AI Agent 智能打标配置」中新建或测试连通性。
                    </p>
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1.5 uppercase tracking-wider">
                      打标平台
                    </label>
                    <select
                      value={tagPlatform}
                      onChange={(e) => setTagPlatform(e.target.value)}
                      className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-violet-600"
                    >
                      <option value="">全部平台</option>
                      {PLATFORMS.filter((p) => p.isSupported).map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1.5 uppercase tracking-wider">
                      打标上限
                    </label>
                    <input
                      type="number"
                      min="1"
                      max="2000"
                      value={tagLimit}
                      onChange={(e) => setTagLimit(Number(e.target.value))}
                      className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-violet-600"
                    />
                    <p className="text-[11px] text-slate-400 mt-1">
                      本次最多处理多少条未打标内容（分批请求模型，每批 20 条）。
                    </p>
                  </div>

                  <div className="pt-1 flex items-center justify-end gap-2.5">
                    <button
                      type="button"
                      onClick={() => setShowTagModal(false)}
                      className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-800 rounded-xl cursor-pointer"
                    >
                      取消
                    </button>
                    <button
                      type="button"
                      onClick={startTagging}
                      disabled={tagStarting || !tagAgentId}
                      className="px-5 py-2.5 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white text-xs font-bold rounded-xl shadow-xs flex items-center gap-1.5 cursor-pointer"
                    >
                      <Sparkles className="w-4 h-4" />
                      {tagStarting ? '提交中...' : '开始打标'}
                    </button>
                  </div>
                </>
              ) : tagPhase === 'running' ? (
                <div className="flex flex-col gap-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-sm font-bold text-slate-900">
                      <Loader2 className="w-4 h-4 text-violet-600 animate-spin" />
                      模型打标进行中...
                    </div>
                    <button
                      type="button"
                      onClick={stopTagging}
                      className="px-3 py-1.5 rounded-xl text-xs font-semibold bg-slate-100 text-slate-600 hover:bg-rose-50 hover:text-rose-600 transition-colors cursor-pointer"
                    >
                      停止
                    </button>
                  </div>

                  {/* 实时进度 */}
                  <div>
                    <div className="flex items-center justify-between text-xs text-slate-500 mb-1.5">
                      <span>
                        已处理 <strong className="text-slate-800">{tagProgress.processed}</strong> / {tagProgress.limit || tagLimit} 条
                      </span>
                      <span>
                        已打标 <strong className="text-violet-600">{tagProgress.tagged}</strong> 条
                      </span>
                    </div>
                    <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-violet-500 rounded-full transition-all duration-500"
                        style={{ width: `${Math.min(100, (tagProgress.processed / (tagProgress.limit || tagLimit)) * 100)}%` }}
                      />
                    </div>
                  </div>

                  {/* 每批打标结果（SSE 实时追加，自动滚动到底部） */}
                  <div ref={tagListRef} className="max-h-56 overflow-y-auto border border-slate-100 rounded-2xl divide-y divide-slate-50 bg-slate-50/50">
                    {tagProgress.results.length === 0 ? (
                      <div className="py-6 text-center text-xs text-slate-400">
                        等待第一批结果（每批 20 条，取决于模型响应速度）...
                      </div>
                    ) : (
                      tagProgress.results.map((r, i) => (
                        <div key={i} className="px-3.5 py-2.5 flex flex-col gap-1 anim-row-enter">
                          <div className="text-xs font-medium text-slate-800 line-clamp-1">{r.title}</div>
                          <div className="flex flex-wrap gap-1">
                            {r.tags.map((t) => (
                              <span key={t} className="px-1.5 py-0.5 rounded bg-violet-50 text-violet-600 text-[10px] font-medium border border-violet-100">
                                #{t}
                              </span>
                            ))}
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                  <p className="text-[11px] text-slate-400 text-right">
                    任务 ID：<span className="font-mono">{tagResult?.taskId}</span>
                  </p>
                </div>
              ) : tagPhase === 'success' ? (
                <div className="py-6 flex flex-col items-center gap-3 text-center">
                  <CheckCircle2 className="w-10 h-10 text-emerald-500" />
                  <div className="text-sm font-bold text-slate-900">打标完成</div>
                  <p className="text-xs text-slate-500">
                    共处理 <strong className="text-slate-800">{tagResult?.processed}</strong> 条，成功打标{' '}
                    <strong className="text-slate-800">{tagResult?.tagged}</strong> 条，列表与标签统计已刷新。
                  </p>
                  <button
                    type="button"
                    onClick={() => setShowTagModal(false)}
                    className="mt-1 px-5 py-2.5 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-xl cursor-pointer"
                  >
                    完成
                  </button>
                </div>
              ) : (
                <div className="py-6 flex flex-col items-center gap-3 text-center">
                  <AlertTriangle className="w-10 h-10 text-rose-500" />
                  <div className="text-sm font-bold text-slate-900">打标失败</div>
                  <p className="text-xs text-rose-600 break-all">{tagResult?.error || '未知错误'}</p>
                  <button
                    type="button"
                    onClick={() => {
                      setTagPhase('idle');
                      setTagResult(null);
                    }}
                    className="mt-1 px-5 py-2.5 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-xl cursor-pointer"
                  >
                    返回重试
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
