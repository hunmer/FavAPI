import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import {transformAsync, type BabelFileResult} from '@babel/core';
import {inspectorServer} from '@react-dev-inspector/vite-plugin';
import {defineConfig, type Plugin} from 'vite';

// 后端 FastAPI 服务地址（开发模式下 /api 代理过去；生产构建产物由后端直接托管）
const BACKEND = process.env.FAVAPI_BACKEND || 'http://127.0.0.1:8300';

const root = path.resolve(__dirname);

// 给每个 JSX 节点注入 data-inspector-line/-column/-relative-path 源码位置
// 属性，DevInspector 点击定位依赖它们。仅 dev 生效，生产构建不受影响。
// 路径统一用正斜杠：Windows 反斜杠经过多轮转义会不稳定，
// 且正斜杠在 path.resolve 与编辑器 CLI 中跨平台通用。
function inspectorTransform(): Plugin {
  return {
    name: 'react-dev-inspector-transform',
    apply: 'serve',
    enforce: 'pre',
    async transform(code, id) {
      const [file] = id.split('?');
      if (!/\.tsx?$/.test(file) || file.includes('node_modules')) return;
      const relativePath = path.relative(root, file).replaceAll('\\', '/');
      const result: BabelFileResult | null = await transformAsync(code, {
        filename: file,
        sourceType: 'module',
        parserOpts: {plugins: ['typescript', 'jsx', 'decorators-legacy']},
        plugins: [
          ({types: t}: {types: typeof import('@babel/core').types}) => ({
            visitor: {
              JSXOpeningElement(nodePath: any) {
                const name = nodePath.node.name;
                if (
                  (t.isJSXIdentifier(name) && name.name.endsWith('Fragment')) ||
                  (t.isJSXMemberExpression(name) &&
                    name.property.name.endsWith('Fragment'))
                ) {
                  return;
                }
                const line = nodePath.node.loc?.start.line;
                const column = nodePath.node.loc?.start.column;
                if (line == null || column == null) return;
                nodePath.node.attributes.unshift(
                  t.jsxAttribute(
                    t.jsxIdentifier('data-inspector-line'),
                    t.stringLiteral(String(line)),
                  ),
                  t.jsxAttribute(
                    t.jsxIdentifier('data-inspector-column'),
                    t.stringLiteral(String(column)),
                  ),
                  t.jsxAttribute(
                    t.jsxIdentifier('data-inspector-relative-path'),
                    t.stringLiteral(relativePath),
                  ),
                );
              },
            },
          }),
        ],
        sourceMaps: true,
      });
      if (!result?.code) return;
      return {code: result.code, map: result.map ?? null};
    },
  };
}

export default defineConfig(() => {
  return {
    plugins: [
      react(),
      tailwindcss(),
      inspectorTransform(),
      // 提供 /__open-stack-frame-in-editor 路由，配合 DevInspector 组件实现
      // 点击页面元素后在编辑器中打开源码。编辑器由 REACT_EDITOR 环境变量
      // 指定，默认 `code`（VS Code）。仅 dev 生效。
      inspectorServer(),
    ],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
      },
    },
    server: {
      port: 3000,
      host: '0.0.0.0',
      proxy: {
        '/api': {target: BACKEND, changeOrigin: true},
      },
    },
  };
});
