/**
 * 工单16-20 延伸 · 平台化双端重构（批次 0 建立，批次 6 强化）
 * 守护「已实现路由映射」与注册表的一致性：路径拼错会导致页面永不渲染。
 *
 * 批次 0 时这里只断言「映射键 ⊆ 注册表路径」（防拼错）；
 * 批次 6 起两端 19 条路由全部实现，因此反过来断言**全覆盖**（防漏接线）——
 * 这个方向的不变量更有价值：漏一条会让页面悄悄退回"建设中"，而没人会注意到。
 */
import { describe, expect, it } from 'vitest'
import { READY_ROUTES } from './readyRoutes'
import { ROUTES } from './routes'

describe('已实现路由映射', () => {
  it('映射表中的每个路径都必须在注册表里，否则该路径永远不会被渲染', () => {
    const known = new Set(ROUTES.map((route) => route.path))
    for (const path of Object.keys(READY_ROUTES)) {
      expect(known.has(path), `未注册的路径：${path}`).toBe(true)
    }
  })

  it('全覆盖：注册表的每条路由都已接线，不存在"建设中"占位页', () => {
    const implemented = new Set(Object.keys(READY_ROUTES))
    const missing = ROUTES.map((route) => route.path).filter((path) => !implemented.has(path))
    expect(missing, `以下路径尚未接线：${missing.join('、')}`).toEqual([])
  })

  it('映射表中的每个值都是可渲染的 React 元素', () => {
    for (const [path, element] of Object.entries(READY_ROUTES)) {
      expect(element, path).toBeTruthy()
      expect(typeof element, path).toBe('object')
    }
  })
})
