import React, { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { Tag } from 'lucide-react';
import * as api from '../../api';

interface GroupEditDialogProps {
  secUid: string;
  nickname?: string | null;
  /** 打开时预填的分组名（空 = 未分组） */
  initialGroup?: string;
  /** 已有分组候选（datalist 建议） */
  groups?: { group_name: string; count: number }[];
  onClose: () => void;
  /** 保存成功回调（group 为新分组名，空串 = 移出分组） */
  onSaved?: (group: string) => void;
  /** 保存失败提示（不传则静默关闭不报错） */
  onError?: (message: string) => void;
}

/** 特别关注博主的分组设置弹窗：添加成功后指定分组 / 列表卡片改分组 共用。 */
export const GroupEditDialog: React.FC<GroupEditDialogProps> = ({
  secUid,
  nickname,
  initialGroup = '',
  groups = [],
  onClose,
  onSaved,
  onError,
}) => {
  const [value, setValue] = useState(initialGroup);
  const [saving, setSaving] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const save = async () => {
    if (saving) return;
    setSaving(true);
    try {
      await api.updateFollowAuthor(secUid, { group_name: value.trim() });
      onSaved?.(value.trim());
      onClose();
    } catch (e: any) {
      (onError ?? (() => {}))(e.message || '分组保存失败');
    } finally {
      setSaving(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onClose}
    >
      <motion.div
        initial={{ scale: 0.95, y: 12 }}
        animate={{ scale: 1, y: 0 }}
        exit={{ scale: 0.95, y: 12 }}
        transition={{ type: 'spring', stiffness: 320, damping: 30 }}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-sm bg-white dark:bg-[#111622] rounded-3xl border border-slate-200 dark:border-slate-800 shadow-2xl p-5"
      >
        <h3 className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-1.5">
          <Tag className="w-4 h-4 text-indigo-500" />
          设置「{(nickname || secUid.slice(0, 16) + '…')}」的分组
        </h3>
        <input
          ref={inputRef}
          list="follow-group-options"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="输入分组名（留空 = 未分组）"
          onKeyDown={(e) => e.key === 'Enter' && save()}
          className="w-full mt-3 px-3.5 py-2.5 rounded-xl text-xs bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 outline-none border-0"
        />
        <datalist id="follow-group-options">
          {groups.map((g) => (
            <option key={g.group_name} value={g.group_name}>
              {g.group_name}（{g.count}）
            </option>
          ))}
        </datalist>
        <div className="flex justify-end gap-2 mt-4">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 transition-colors cursor-pointer"
          >
            跳过
          </button>
          <button
            onClick={save}
            disabled={saving}
            className="px-4 py-2 rounded-xl text-xs font-semibold bg-indigo-600 text-white hover:bg-indigo-500 active:scale-95 transition-all disabled:opacity-50 cursor-pointer"
          >
            {saving ? '保存中…' : '保存'}
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
};

/** AnimatePresence 包装版（keep mounted 语义由调用方控制） */
export const GroupEditDialogPresence: React.FC<GroupEditDialogProps & { open: boolean }> = ({
  open,
  ...props
}) => (
  <AnimatePresence>{open && <GroupEditDialog {...props} />}</AnimatePresence>
);
