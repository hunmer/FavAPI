import React, { useMemo, useState } from 'react';
import { motion } from 'motion/react';
import { CheckCircle2, Loader2, UserPlus } from 'lucide-react';
import * as api from '../../api';
import { Account } from '../../types';
import { PLATFORMS } from '../../data/platforms';

interface AddFollowsDialogProps {
  accounts: Account[];
  showToast: (msg: string, type?: 'success' | 'info' | 'error') => void;
  onClose: () => void;
  /** 全部处理完成后回调（父级触发特别关注列表刷新） */
  onAdded: () => void;
}

type ItemStatus = 'pending' | 'ok' | 'exists' | 'failed';

type ParsedItem = {
  url: string;
  key: string; // platform:secUid（无效行为 invalid:url），结果状态按它索引
  platform: string;
  secUid: string;
  error: string;
};

const platformName = (id: string) => PLATFORMS.find((p) => p.id === id)?.name || id;

/** 从一行输入提取博主主页链接，解析出平台与用户主键（与后端 follows_validate_uid 对齐）。 */
function parseLine(line: string): { platform: string; secUid: string } | { error: string } {
  const m = line.match(/https?:\/\/\S+/i);
  if (!m) return { error: '未识别到链接' };
  let u: URL;
  try {
    u = new URL(m[0]);
  } catch {
    return { error: '链接格式无效' };
  }
  const host = u.hostname.replace(/^www\./i, '').toLowerCase();
  const segs = u.pathname.split('/').filter(Boolean).map(decodeURIComponent);

  if (host.endsWith('douyin.com')) {
    const id = segs[0] === 'user' ? segs[1] || '' : '';
    if (/^MS4[A-Za-z0-9_-]+$/.test(id)) return { platform: 'douyin', secUid: id };
    return { error: '需 douyin.com/user/MS4… 主页链接（短链/分享文案请先在浏览器打开后再复制）' };
  }
  if (host.endsWith('bilibili.com')) {
    if (/^\d+$/.test(segs[0] || '')) return { platform: 'bilibili', secUid: segs[0] };
    return { error: '需 space.bilibili.com/{纯数字 mid} 博主空间链接' };
  }
  if (host.endsWith('kuaishou.com')) {
    const id = segs[0] === 'profile' ? segs[1] || '' : '';
    if (/^3x[0-9a-z]{10,}$/.test(id)) return { platform: 'kuaishou', secUid: id };
    return { error: '需 kuaishou.com/profile/{博主 ID} 主页链接' };
  }
  if (host.endsWith('xiaohongshu.com')) {
    const id = segs[0] === 'user' && segs[1] === 'profile' ? segs[2] || '' : '';
    if (/^[0-9a-f]{24}$/i.test(id)) return { platform: 'xiaohongshu', secUid: id };
    return { error: '需 xiaohongshu.com/user/profile/{用户 ID} 主页链接' };
  }
  if (host.endsWith('instagram.com')) {
    const name = segs[0] || '';
    const reserved = new Set(['p', 'reels', 'stories', 'explore', 'accounts', 'tv', 'direct', 'about']);
    if (name && !reserved.has(name) && /^[A-Za-z0-9._]{1,30}$/.test(name)) {
      return { platform: 'instagram', secUid: name };
    }
    return { error: '需 instagram.com/{用户名} 主页链接' };
  }
  if (host.endsWith('tiktok.com')) {
    return { error: 'TikTok 主页链接只有 @用户名，无法提取主键 secUid，暂不支持' };
  }
  if (host.endsWith('threads.net')) {
    return { error: 'Threads 主页链接只有 @用户名，无法提取数字用户 ID，暂不支持' };
  }
  if (host.endsWith('youtube.com')) {
    const id = segs[0] === 'channel' ? segs[1] || '' : '';
    if (/^UC[A-Za-z0-9_-]{22}$/.test(id)) return { platform: 'youtube', secUid: id };
    return { error: '需 youtube.com/channel/UC… 频道链接（@handle 页面地址拿不到频道 ID）' };
  }
  return { error: `不支持的平台：${host}` };
}

/** 添加特别关注弹窗（特别关注页 Header「添加关注」入口）：粘贴博主主页 URL 列表，
 *  实时解析平台与用户主键，按平台绑定可选浏览账号后批量添加。 */
export const AddFollowsDialog: React.FC<AddFollowsDialogProps> = ({ accounts, showToast, onClose, onAdded }) => {
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  // 每条解析结果的添加状态（key → status），与 items 分离以便提交时实时刷新行状态
  const [results, setResults] = useState<Record<string, { status: ItemStatus; reason?: string }>>({});
  const [accountByPlatform, setAccountByPlatform] = useState<Record<string, string>>({});

  // 逐行解析 + 输入内去重（platform:secUid 相同只保留首条）
  const items = useMemo<ParsedItem[]>(() => {
    const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
    const seen = new Set<string>();
    const out: ParsedItem[] = [];
    for (const line of lines) {
      const r = parseLine(line);
      const platform = 'platform' in r ? r.platform : '';
      const secUid = 'secUid' in r ? r.secUid : '';
      const key = platform && secUid ? `${platform}:${secUid}` : `invalid:${line}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({ url: line, key, platform, secUid, error: 'error' in r ? r.error : '' });
    }
    return out;
  }, [text]);

  const validItems = items.filter((i) => !i.error);
  const platforms = useMemo(
    () => [...new Set(validItems.map((i) => i.platform))],
    [validItems]
  );

  const accountOptions = (platform: string) =>
    accounts.filter((a) => a.platform === platform && a.status === 'active');

  /** 平台绑定账号：未手动选择且该平台恰有一个启用账号时默认选中（浏览/同步需要） */
  const effectiveAccount = (platform: string): string => {
    if (accountByPlatform[platform]) return accountByPlatform[platform];
    const opts = accountOptions(platform);
    return opts.length === 1 ? opts[0].id : '';
  };

  const submit = async () => {
    if (!validItems.length || busy) return;
    setBusy(true);
    const statuses: ItemStatus[] = [];
    for (const item of validItems) {
      let entry: { status: ItemStatus; reason?: string };
      try {
        await api.addFollowAuthor({
          sec_uid: item.secUid,
          platform: item.platform,
          account_id: effectiveAccount(item.platform),
        });
        entry = { status: 'ok' };
      } catch (e: any) {
        if (/已在特别关注/.test(e.message || '')) {
          entry = { status: 'exists' };
        } else {
          entry = { status: 'failed', reason: e.message || '添加失败' };
        }
      }
      statuses.push(entry.status);
      setResults((prev) => ({ ...prev, [item.key]: entry }));
    }
    setBusy(false);
    onAdded();
    const ok = statuses.filter((s) => s === 'ok').length;
    const exists = statuses.filter((s) => s === 'exists').length;
    const failed = statuses.filter((s) => s === 'failed').length;
    if (!failed) {
      showToast(`已添加 ${ok} 位博主${exists ? `，${exists} 位已存在` : ''}`);
      onClose();
    } else {
      // 失败明细展示在预览列表行内（弹窗保持打开），toast 只汇总
      showToast(`添加 ${ok} 位、已存在 ${exists} 位、失败 ${failed} 位`, 'error');
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4"
      onClick={() => !busy && onClose()}
    >
      <motion.div
        initial={{ scale: 0.95, y: 12 }}
        animate={{ scale: 1, y: 0 }}
        exit={{ scale: 0.95, y: 12 }}
        transition={{ type: 'spring', stiffness: 320, damping: 30 }}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-lg bg-white dark:bg-[#161B26] rounded-[28px] p-6 shadow-2xl border border-slate-100 dark:border-slate-800 space-y-4 max-h-[88vh] flex flex-col"
      >
        <h3 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
          <UserPlus className="w-4 h-4 text-indigo-500" />
          添加特别关注
        </h3>

        <div>
          <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5">
            博主主页链接（每行一个，可粘贴多个）
          </label>
          <textarea
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setResults({}); // 输入变更后上次的结果状态作废
            }}
            rows={4}
            placeholder={'https://www.douyin.com/user/MS4wLjABAAAA…\nhttps://space.bilibili.com/12345678\nhttps://www.instagram.com/username/'}
            disabled={busy}
            className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 text-xs font-mono bg-transparent dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-slate-900 dark:focus:ring-sky-500 resize-y"
          />
          <p className="text-[11px] text-slate-400 mt-1">
            支持抖音 / B站 / 快手 / 小红书 / Instagram / YouTube 主页链接；TikTok、Threads 主页地址不含用户主键，暂不支持
          </p>
        </div>

        {/* 解析预览 */}
        {items.length > 0 && (
          <div className="flex-1 min-h-0 overflow-y-auto rounded-xl border border-slate-100 dark:border-slate-800 divide-y divide-slate-100 dark:divide-slate-800">
            {items.map((item) => {
              const result = results[item.key];
              const status: ItemStatus = result?.status || 'pending';
              return (
              <div key={item.key} className="flex items-center gap-2 px-3 py-2 text-xs">
                {item.error ? (
                  <>
                    <span className="text-rose-500 shrink-0">✗</span>
                    <span className="text-slate-400 dark:text-slate-500 truncate flex-1" title={item.url}>{item.url}</span>
                    <span className="text-rose-600 dark:text-rose-400 text-right max-w-[55%]">{item.error}</span>
                  </>
                ) : (
                  <>
                    {status === 'ok' ? (
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                    ) : status === 'exists' ? (
                      <span className="text-amber-500 shrink-0">✓</span>
                    ) : status === 'failed' ? (
                      <span className="text-rose-500 shrink-0">✗</span>
                    ) : busy ? (
                      <Loader2 className="w-3.5 h-3.5 text-slate-400 animate-spin shrink-0" />
                    ) : (
                      <span className="w-3.5 h-3.5 rounded-full border border-slate-300 dark:border-slate-600 shrink-0" />
                    )}
                    <span className="font-semibold text-slate-600 dark:text-slate-300 shrink-0">
                      {platformName(item.platform)}
                    </span>
                    <span className="font-mono text-slate-500 dark:text-slate-400 truncate flex-1" title={item.secUid}>
                      {item.secUid}
                    </span>
                    {status === 'exists' && <span className="text-amber-600 dark:text-amber-400 shrink-0">已存在</span>}
                    {status === 'failed' && (
                      <span className="text-rose-600 dark:text-rose-400 text-right max-w-[45%] truncate" title={result?.reason}>
                        {result?.reason}
                      </span>
                    )}
                  </>
                )}
              </div>
              );
            })}
          </div>
        )}

        {/* 平台浏览账号绑定（可选，浏览主页作品与同步需要） */}
        {platforms.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs font-bold text-slate-700 dark:text-slate-300">浏览账号（可选）</p>
            {platforms.map((p) => {
              const opts = accountOptions(p);
              return (
                <div key={p} className="flex items-center gap-2">
                  <span className="text-xs text-slate-500 dark:text-slate-400 w-28 shrink-0 truncate">{platformName(p)}</span>
                  {opts.length === 0 ? (
                    <span className="text-[11px] text-amber-600 dark:text-amber-400">
                      该平台暂无启用账号，添加后无法浏览主页作品与同步（可在账号管理页添加）
                    </span>
                  ) : (
                    <select
                      value={effectiveAccount(p)}
                      onChange={(e) => setAccountByPlatform((m) => ({ ...m, [p]: e.target.value }))}
                      disabled={busy}
                      className="flex-1 px-3 py-1.5 rounded-xl border border-slate-200 dark:border-slate-700 text-xs bg-transparent dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-slate-900 dark:focus:ring-sky-500 cursor-pointer"
                    >
                      <option value="">不绑定</option>
                      {opts.map((a) => (
                        <option key={a.id} value={a.id}>{a.name}</option>
                      ))}
                    </select>
                  )}
                </div>
              );
            })}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-1">
          <button
            onClick={() => !busy && onClose()}
            disabled={busy}
            className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 transition-colors cursor-pointer disabled:opacity-50"
          >
            {busy ? '关闭' : '取消'}
          </button>
          <button
            onClick={submit}
            disabled={busy || !validItems.length}
            className="px-5 py-2 rounded-xl text-xs font-bold bg-slate-900 dark:bg-sky-600 text-white hover:opacity-90 active:scale-95 transition-all disabled:opacity-50 inline-flex items-center gap-1.5 cursor-pointer"
          >
            {busy && <span className="w-3 h-3 border-2 border-white/40 border-t-white rounded-full animate-spin" />}
            {busy ? '添加中…' : validItems.length ? `添加 ${validItems.length} 位博主` : '添加'}
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
};
