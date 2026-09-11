import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import {defineConfig} from 'vite';

// 后端 FastAPI 服务地址（开发模式下 /api 代理过去；生产构建产物由后端直接托管）
const BACKEND = process.env.FAVAPI_BACKEND || 'http://127.0.0.1:8300';

export default defineConfig(() => {
  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
      },
    },
    server: {
      port: 3000,
      host: '0.0.0.0',
      proxy: {
        '/api': { target: BACKEND, changeOrigin: true },
      },
    },
  };
});
