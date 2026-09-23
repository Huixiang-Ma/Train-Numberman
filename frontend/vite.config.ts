import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 工单18 · 数字人导览前端
// 通过代理把 /api 转发到阶段二/三后端（含 WebSocket），避免跨域配置
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 8200,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8100',
        changeOrigin: true,
        ws: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
