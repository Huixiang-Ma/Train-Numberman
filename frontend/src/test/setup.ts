// 工单16-20 延伸 · 平台化双端重构（批次 0）
// 测试环境初始化。
import '@testing-library/jest-dom/vitest'

/**
 * jsdom 不实现 window.matchMedia，而 AvatarStage 用它读取 prefers-reduced-motion，
 * 缺失时会在挂载阶段抛错、让整条组件树渲染失败。这是测试环境缺口，不是产品缺陷，
 * 因此按 jsdom 官方推荐补一个最小实现（真正的媒体查询语义在浏览器里由浏览器提供）。
 */
if (typeof window !== 'undefined' && typeof window.matchMedia !== 'function') {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia
}
