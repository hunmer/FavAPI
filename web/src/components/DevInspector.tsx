// 开发环境专用的 React 元素定位器，生产构建下不渲染任何内容。
//
// 开发模式下按快捷键（Win/Linux 为 Ctrl+Shift+Alt+C，macOS 为
// Ctrl+Shift+Command+C）或点击右下角悬浮的光标按钮进入定位模式，
// 悬停高亮元素后点击，即可在编辑器中打开该组件的源码位置。
// 编辑器通过 REACT_EDITOR 环境变量指定，默认 `code`（VS Code）。
//
// 源码位置有两条解析路径，最终都交给 gotoServerEditor：
//   1. vite.config.ts 中 inspectorTransform 注入的 data-inspector-* 属性
//      （主要路径，精确到 JSX 节点）；
//   2. React Fiber 的 _debugSource 兜底（React 19.2 起已无此字段，
//      保留以兼容旧版 React）。

import {useEffect, useState} from 'react';
import {gotoServerEditor, Inspector} from 'react-dev-inspector';
import {MousePointer2} from 'lucide-react';

type ReactFiber = {
  return?: ReactFiber | null;
  _debugSource?: {
    fileName?: string;
    lineNumber?: number;
    columnNumber?: number;
  };
  _debugOwner?: ReactFiber | null;
};

type FiberElement = HTMLElement & {
  [key: string]: ReactFiber | undefined;
};

function getFiber(element: HTMLElement | null): ReactFiber | undefined {
  if (!element) return undefined;

  const fiberKey = Object.keys(element).find(
    (key) =>
      key.startsWith('__reactFiber$') ||
      key.startsWith('__reactInternalInstance$'),
  );

  if (fiberKey) return (element as FiberElement)[fiberKey];
  return getFiber(element.parentElement);
}

function getCodeInfo(element: HTMLElement) {
  const sourceElement = element.closest<HTMLElement>(
    '[data-inspector-relative-path]',
  );

  if (sourceElement?.dataset.inspectorRelativePath) {
    return {
      relativePath: sourceElement.dataset.inspectorRelativePath,
      lineNumber: sourceElement.dataset.inspectorLine ?? '1',
      columnNumber: sourceElement.dataset.inspectorColumn ?? '1',
    };
  }

  let fiber = getFiber(element);

  while (fiber) {
    const source = fiber._debugSource ?? fiber._debugOwner?._debugSource;

    if (source?.fileName && source.lineNumber) {
      return {
        absolutePath: source.fileName,
        lineNumber: String(source.lineNumber),
        columnNumber: String(source.columnNumber ?? 1),
      };
    }

    fiber = fiber.return ?? undefined;
  }

  return undefined;
}

export function DevInspector() {
  const [active, setActive] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!active) return;

    const handleClick = (event: MouseEvent) => {
      event.preventDefault();
      event.stopPropagation();

      const target = event.target;
      if (!(target instanceof HTMLElement)) return;

      const codeInfo = getCodeInfo(target);
      setActive(false);

      if (codeInfo) {
        gotoServerEditor(codeInfo);
      }
    };

    window.addEventListener('click', handleClick, true);
    return () => window.removeEventListener('click', handleClick, true);
  }, [active]);

  // 生产构建中整体裁剪 —— Vite 会静态替换 import.meta.env.DEV。
  if (!import.meta.env.DEV) return null;
  if (!mounted) return null;

  const isMac = /Mac|iPhone|iPad|iPod/i.test(navigator.platform);
  const inspectorKeys = isMac
    ? ['Ctrl', 'Shift', 'Command', 'C']
    : ['Ctrl', 'Shift', 'Alt', 'C'];
  const hotkey = inspectorKeys.join(' + ');

  return (
    <>
      <Inspector
        keys={inspectorKeys}
        active={active}
        onActiveChange={setActive}
        onClickElement={() => {}}
        onInspectElement={({codeInfo}) => {
          gotoServerEditor(codeInfo);
        }}
      />
      <button
        type="button"
        onClick={() => setActive((value) => !value)}
        aria-pressed={active}
        title={`元素定位（${hotkey}）：点击页面元素在编辑器中打开对应源码`}
        className="fixed bottom-3 right-3 z-[2147483647] flex h-8 w-8 items-center justify-center rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow hover:bg-slate-100 dark:hover:bg-slate-700"
      >
        <MousePointer2
          className={active ? 'text-sky-500' : 'text-slate-400 dark:text-slate-500'}
          size={16}
        />
      </button>
    </>
  );
}
