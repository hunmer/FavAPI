import React, { useLayoutEffect, useRef, useState } from 'react';
import { useDismiss } from '../hooks/useDismiss';

interface PopoverProps {
  open: boolean;
  onClose: () => void;
  /** 浮层内容；open=false 时不渲染 */
  content: React.ReactNode;
  /** 触发元素（按钮等）；开合状态由外部控制 */
  children: React.ReactNode;
  /** 浮层附加类名（宽度、圆角、阴影等） */
  panelClassName?: string;
  /** fixed 定位：浮层按 viewport 坐标挂在触发器下方，适合触发器位于 overflow 裁剪容器（表格滚动区等）内；默认 absolute 相对触发器右对齐 */
  fixed?: boolean;
}

/**
 * 通用弹出层：触发元素与浮层同容器绝对定位。
 * 点击浮层外部任意位置（含滚动 / 右键 / 窗口缩放）自动关闭；
 * 点击容器内部（触发按钮、浮层本身）不触发外部关闭，交由元素自身 onClick 处理。
 */
export const Popover: React.FC<PopoverProps> = ({
  open,
  onClose,
  content,
  children,
  panelClassName = '',
  fixed = false,
}) => {
  const rootRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  useDismiss(onClose, open, rootRef);

  // fixed 模式在 paint 前测量触发器位置，浮层不会被 overflow 祖先裁剪
  useLayoutEffect(() => {
    if (!open || !fixed) return;
    const rect = rootRef.current?.getBoundingClientRect();
    if (rect) setPos({ top: rect.bottom + 8, left: rect.left });
  }, [open, fixed]);

  // fixed 模式下拿到坐标前不渲染浮层：panel 以 static 渲染会撑开 rootRef，
  // 测得的 rect.bottom 把浮层自身高度也算进去，导致首次弹出位置偏下
  const panelVisible = open && (!fixed || pos !== null);

  return (
    <div ref={rootRef} className="relative">
      {children}
      {panelVisible && (
        <div
          style={fixed && pos ? { position: 'fixed', top: pos.top, left: pos.left } : undefined}
          className={`${fixed ? '' : 'absolute right-0'} mt-2 z-50 anim-modal-enter ${panelClassName}`}
        >
          {content}
        </div>
      )}
    </div>
  );
};
