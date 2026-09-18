import { FetchTargetSpec, PlatformId } from '../types';

export interface PlatformMeta {
  id: PlatformId;
  name: string;
  icon: string;
  color: string;
  badgeBg: string;
  isSupported: boolean;
  tagline: string;
  apiFetch?: boolean; // 收藏抓取支持 API 直连方式（后端 adapter.api_fetch_implemented）
  followsApi?: boolean; // 支持特别关注体系（关注列表 / 博主主页作品 / 一键同步）
  fetchTargets?: FetchTargetSpec[]; // 可抓取入库的列表目标（后端 /platforms 下发）
}

/** 后端不可用 / 平台信息未加载时的默认抓取目标（仅收藏列表）。 */
export const DEFAULT_FETCH_TARGETS: FetchTargetSpec[] = [
  {
    action: 'list_favorites',
    name: '抓取收藏列表',
    description: '抓取当前账号收藏列表并入库',
    source: '',
    params: [
      { key: 'count', label: '抓取数量 (0 为全部)', type: 'number', required: false, placeholder: '默认全部', help: '返回条数上限；留空或 0 抓取全部' },
      { key: 'date_from', label: '收藏日期从', type: 'date', required: false, placeholder: '', help: '可选；平台无收藏时间时按发布时间判定' },
      { key: 'date_to', label: '收藏日期至', type: 'date', required: false, placeholder: '', help: '可选，闭区间（含当天）' },
    ],
  },
];

export const PLATFORMS: PlatformMeta[] = [
  {
    id: 'bilibili',
    name: 'Bilibili 哔哩哔哩',
    icon: 'bili',
    color: '#00AEEC',
    badgeBg: 'bg-[#EBF7FD] text-[#00AEEC] border-[#B9E6FA]',
    isSupported: true,
    tagline: '支持多收藏夹全量与增量同步、反风控间隔调节',
    followsApi: true,
  },
  {
    id: 'xiaohongshu',
    name: '小红书 Xiaohongshu',
    icon: 'xhs',
    color: '#FF2442',
    badgeBg: 'bg-[#FFF0F2] text-[#FF2442] border-[#FFCCD4]',
    isSupported: true,
    tagline: '支持专辑与笔记收藏抓取、高清图文及视频入库',
    apiFetch: true,
  },
  {
    id: 'douyin',
    name: '抖音 Douyin',
    icon: 'douyin',
    color: '#161823',
    badgeBg: 'bg-[#F2F2F4] text-[#161823] border-[#DCDDE1]',
    isSupported: true,
    tagline: '支持个人合集与点赞/收藏短视频多维度解析',
    apiFetch: true,
    followsApi: true,
  },
  {
    id: 'kuaishou',
    name: '快手 Kuaishou',
    icon: 'kuaishou',
    color: '#FF7300',
    badgeBg: 'bg-[#FFF3E8] text-[#FF7300] border-[#FFD8B0]',
    isSupported: true,
    tagline: '支持收藏/点赞视频抓取，API 直连与浏览器模拟',
    apiFetch: true,
    followsApi: true,
  },
  {
    id: 'threads',
    name: 'Threads',
    icon: 'threads',
    color: '#000000',
    badgeBg: 'bg-slate-100 text-slate-600 border-slate-200',
    isSupported: true,
    tagline: '已保存帖子收藏抓取，支持 API 直连与浏览器模拟',
    apiFetch: true,
  },
  {
    id: 'tiktok',
    name: 'TikTok',
    icon: 'tiktok',
    color: '#FF0050',
    badgeBg: 'bg-[#FFF0F3] text-[#FF0050] border-[#FFCCD6]',
    isSupported: true,
    tagline: '收藏/点赞视频抓取与用户信息查询，支持 API 直连与浏览器模拟',
    apiFetch: true,
  },
  {
    id: 'zhihu',
    name: '知乎 Zhihu',
    icon: 'zhihu',
    color: '#0066FF',
    badgeBg: 'bg-[#EDF4FF] text-[#0066FF] border-[#C2DBFF]',
    isSupported: true,
    tagline: '支持回答、专栏文章与想法收藏夹 Markdown 提取',
  },
  {
    id: 'weibo',
    name: '微博 Weibo',
    icon: 'weibo',
    color: '#E6162D',
    badgeBg: 'bg-slate-100 text-slate-400 border-slate-200',
    isSupported: false,
    tagline: '博文、快照及微博视频收藏抓取（即将支持）',
  },
  {
    id: 'youtube',
    name: 'YouTube',
    icon: 'yt',
    color: '#FF0000',
    badgeBg: 'bg-slate-100 text-slate-400 border-slate-200',
    isSupported: false,
    tagline: 'Playlists 与 Watch Later 列表抓取（即将支持）',
  },
  {
    id: 'wechat',
    name: '微信收藏 WeChat',
    icon: 'wechat',
    color: '#07C160',
    badgeBg: 'bg-[#ECFDF3] text-[#07C160] border-[#BBF7D0]',
    isSupported: true,
    tagline: '导入 WeChatDataAnalysis 导出的 messages.json 收藏数据',
  },
  {
    id: 'twitter',
    name: 'X (Twitter)',
    icon: 'x',
    color: '#000000',
    badgeBg: 'bg-slate-100 text-slate-400 border-slate-200',
    isSupported: false,
    tagline: 'Bookmarks 书签与媒体归档（即将支持）',
  },
];
