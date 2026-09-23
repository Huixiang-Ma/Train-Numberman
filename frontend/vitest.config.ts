// 工单16-20 延伸 · 平台化双端重构（批次 0）
// 测试配置独立于 vite.config.ts：vite.config.ts 只负责开发服务器与构建，
// 测试需要 jsdom 环境与 setup 文件，混在一起会让两者互相牵制。
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
