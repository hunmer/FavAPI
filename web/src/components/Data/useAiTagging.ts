import { useEffect, useRef, useState } from 'react';
import { Account } from '../../types';
import * as api from '../../api';

/**
 * 一键 AI 打标的状态与流程（自 DataBrowserView 抽离）。
 *
 * SSE 流式接收每批打标结果实时追加到进度；tagProgressRef 同步最新进度，
 * 供停止/异常回调读取（避免闭包陈旧值）。
 */
export function useAiTagging(opts: {
  agents: api.AgentConfigRow[];
  accounts: Account[];
  selectedAccountId: string;
  /** 任务结束（成功/中止）后刷新列表与标签统计 */
  onDone: () => void;
}) {
  const { agents, accounts, selectedAccountId, onDone } = opts;

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
  const tagAbortRef = useRef<AbortController | null>(null);
  // 同步最新进度到 ref，供停止/异常回调读取（避免闭包陈旧值）
  const tagProgressRef = useRef(tagProgress);
  tagProgressRef.current = tagProgress;
  const tagListRef = useRef<HTMLDivElement>(null);

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
      onDone();  // 刷新收藏列表与标签统计
    } catch (err: any) {
      // 用户主动中止：已推流的批次结果保留在进度里
      if (abort.signal.aborted) {
        const latest = tagProgressRef.current;
        setTagPhase('failed');
        setTagResult({ processed: latest.processed, tagged: latest.tagged, error: '已手动停止（已完成批次保留）' });
        onDone();
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

  return {
    showTagModal, setShowTagModal,
    tagAgentId, setTagAgentId,
    tagPlatform, setTagPlatform,
    tagLimit, setTagLimit,
    tagStarting,
    tagPhase, setTagPhase,
    tagResult, setTagResult,
    tagProgress,
    tagListRef,
    openTagModal,
    startTagging,
    stopTagging,
  };
}
