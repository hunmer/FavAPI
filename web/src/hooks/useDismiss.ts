import { useEffect, useRef } from 'react';

/**
 * 弹出菜单/浮层的统一点击外部关闭。
 *
 * 监听挂在 window 捕获（capture）阶段：打开菜单的右键/dots 事件通常带
 * stopPropagation，冒泡阶段的 window 监听收不到，会导致旧菜单不关闭。
 * active 为 false 时不挂监听；onClose 经 ref 透传，无需稳定引用。
 *
 * rootRef（浮层根节点）：捕获阶段先于浮层内按钮的 onClick 执行，若此处
 * 同步 setState 卸载浮层（React 18 对原生监听器里的离散更新同步 flush），
 * 按钮 onClick 将永远不会触发（表现为点击菜单项无反应）。因此点击目标
 * 在浮层内部时跳过关闭，交由菜单项自身的 onClick 处理。
 */
export function useDismiss(
  onClose: () => void,
  active = true,
  rootRef?: React.RefObject<HTMLElement | null>,
) {
  const ref = useRef(onClose);
  ref.current = onClose;

  useEffect(() => {
    if (!active) return;
    const isInside = (e: Event) =>
      !!rootRef?.current && e.target instanceof Node && rootRef.current.contains(e.target);
    const close = (e: Event) => {
      if (e.type === 'click' && isInside(e)) return;
      ref.current();
    };
    window.addEventListener('click', close, true);
    window.addEventListener('contextmenu', close, true);
    window.addEventListener('resize', close);
    window.addEventListener('scroll', close, true);
    return () => {
      window.removeEventListener('click', close, true);
      window.removeEventListener('contextmenu', close, true);
      window.removeEventListener('resize', close);
      window.removeEventListener('scroll', close, true);
    };
  }, [active, rootRef]);
}
