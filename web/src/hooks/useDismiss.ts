import { useEffect, useRef } from 'react';

/**
 * 弹出菜单/浮层的统一点击外部关闭。
 *
 * 监听挂在 window 捕获（capture）阶段：打开菜单的右键/dots 事件通常带
 * stopPropagation，冒泡阶段的 window 监听收不到，会导致旧菜单不关闭。
 * active 为 false 时不挂监听；onClose 经 ref 透传，无需稳定引用。
 */
export function useDismiss(onClose: () => void, active = true) {
  const ref = useRef(onClose);
  ref.current = onClose;

  useEffect(() => {
    if (!active) return;
    const close = () => ref.current();
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
  }, [active]);
}
