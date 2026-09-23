/**
 * 工单16-20 延伸 · 平台化双端重构（批次 0）
 * 路由注册表的不变量测试：路径唯一、导航与路由不漂移、两端不交叉。
 */
import { describe, expect, it } from 'vitest'
import { ROUTES, tocNav, tobNavGroups } from './routes'

describe('路由注册表', () => {
  it('路径唯一，避免后注册的路由被静默覆盖', () => {
    const paths = ROUTES.map((route) => route.path)
    expect(new Set(paths).size).toBe(paths.length)
  })

  it('每条路由都登记了工单依据，便于「建设中」页面如实说明来源', () => {
    for (const route of ROUTES) {
      expect(route.ticket.length, route.path).toBeGreaterThan(0)
      expect(route.label.length, route.path).toBeGreaterThan(0)
    }
  })

  it('ToC 与 ToB 路由不交叉', () => {
    const toc = ROUTES.filter((route) => route.side === 'toc')
    const tob = ROUTES.filter((route) => route.side === 'tob')
    expect(toc.every((route) => !route.path.startsWith('/admin'))).toBe(true)
    expect(tob.every((route) => route.path.startsWith('/admin'))).toBe(true)
  })

  it('ToC 导航项必须来自注册表且带字形', () => {
    expect(tocNav.length).toBeGreaterThan(0)
    for (const item of tocNav) {
      const matched = ROUTES.find((route) => route.path === item.to)
      expect(matched, item.to).toBeDefined()
      expect(matched?.side).toBe('toc')
      expect(matched?.glyph, item.to).toBeTruthy()
    }
  })

  it('ToB 导航按分组聚合，且不出现空分组', () => {
    expect(tobNavGroups.length).toBeGreaterThan(0)
    for (const group of tobNavGroups) {
      expect(group.title.length).toBeGreaterThan(0)
      expect(group.items.length).toBeGreaterThan(0)
      expect(group.items.every((item) => item.to.startsWith('/admin'))).toBe(true)
    }
  })
})
