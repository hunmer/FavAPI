/**
 * 主题色（primary color）运行时切换。
 *
 * 原理：Tailwind v4 的工具类（bg-indigo-600 等）编译为引用 CSS 变量
 * `--color-indigo-*`，在 <html> 上以内联样式覆盖这组变量即可全局换色，
 * 组件零改动。选择存 localStorage，启动时（main.tsx）恢复。
 */

export interface PrimaryPreset {
  id: string;
  name: string;
  /** 覆盖 --color-indigo-{shade} 的完整色板（50~950） */
  shades: Record<'50' | '100' | '200' | '300' | '400' | '500' | '600' | '700' | '800' | '900' | '950', string>;
}

const preset = (
  id: string,
  name: string,
  shades: [string, string, string, string, string, string, string, string, string, string, string],
): PrimaryPreset => ({
  id,
  name,
  shades: {
    '50': shades[0], '100': shades[1], '200': shades[2], '300': shades[3], '400': shades[4],
    '500': shades[5], '600': shades[6], '700': shades[7], '800': shades[8], '900': shades[9], '950': shades[10],
  },
});

/** 内置主题色预设（色值取 Tailwind 默认色板，indigo 为原始默认） */
export const PRIMARY_PRESETS: PrimaryPreset[] = [
  preset('indigo', '靛蓝', ['#eef2ff', '#e0e7ff', '#c7d2fe', '#a5b4fc', '#818cf8', '#6366f1', '#4f46e5', '#4338ca', '#3730a3', '#312e81', '#1e1b4b']),
  preset('blue', '蔚蓝', ['#eff6ff', '#dbeafe', '#bfdbfe', '#93c5fd', '#60a5fa', '#3b82f6', '#2563eb', '#1d4ed8', '#1e40af', '#1e3a8a', '#172554']),
  preset('cyan', '青碧', ['#ecfeff', '#cffafe', '#a5f3fc', '#67e8f9', '#22d3ee', '#06b6d4', '#0891b2', '#0e7490', '#155e75', '#164e63', '#083344']),
  preset('emerald', '翠绿', ['#ecfdf5', '#d1fae5', '#a7f3d0', '#6ee7b7', '#34d399', '#10b981', '#059669', '#047857', '#065f46', '#064e3b', '#022c22']),
  preset('amber', '琥珀', ['#fffbeb', '#fef3c7', '#fde68a', '#fcd34d', '#fbbf24', '#f59e0b', '#d97706', '#b45309', '#92400e', '#78350f', '#451a03']),
  preset('rose', '玫红', ['#fff1f2', '#ffe4e6', '#fecdd3', '#fda4af', '#fb7185', '#f43f5e', '#e11d48', '#be123c', '#9f1239', '#881337', '#4c0519']),
  preset('violet', '罗兰紫', ['#f5f3ff', '#ede9fe', '#ddd6fe', '#c4b5fd', '#a78bfa', '#8b5cf6', '#7c3aed', '#6d28d9', '#5b21b6', '#4c1d95', '#2e1065']),
];

const STORAGE_KEY = 'favapi_primary';

/** 应用主题色：覆盖 <html> 上的 --color-indigo-* 并持久化；未知 id 回退默认 */
export const applyPrimaryColor = (id: string) => {
  const p = PRIMARY_PRESETS.find((x) => x.id === id) ?? PRIMARY_PRESETS[0];
  const root = document.documentElement;
  for (const [shade, hex] of Object.entries(p.shades)) {
    root.style.setProperty(`--color-indigo-${shade}`, hex);
  }
  localStorage.setItem(STORAGE_KEY, p.id);
  return p;
};

/** 启动时恢复已保存的主题色（main.tsx 调用，仅覆盖样式不写回存储） */
export const readPrimaryColorId = (): string =>
  localStorage.getItem(STORAGE_KEY) ?? PRIMARY_PRESETS[0].id;
