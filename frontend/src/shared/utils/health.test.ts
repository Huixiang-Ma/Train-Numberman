/**
 * 工单16-20 延伸 · 平台化双端重构（批次 0）
 * health.ts 的测试。含按后端 /readyz 实机形状（{"ok": bool, ...}）构造的夹具。
 */
import { describe, expect, it } from 'vitest'
import { collectChecks, formatValue, inferTone } from './health'

describe('inferTone', () => {
  it('布尔直接映射为可用与待确认', () => {
    expect(inferTone(true)).toBe('ok')
    expect(inferTone(false)).toBe('warn')
  })

  it('否定语义优先于其中包含的肯定词', () => {
    // "not ready" 含 "ready"，若不先判否定就会误报为可用
    expect(inferTone('not ready')).toBe('down')
    expect(inferTone('no data')).toBe('down')
    expect(inferTone('ready')).toBe('ok')
  })

  it('识别失败、降级与正常关键字', () => {
    expect(inferTone('milvus unavailable')).toBe('down')
    expect(inferTone('embedding warming')).toBe('warn')
    expect(inferTone('postgres healthy')).toBe('ok')
  })

  it('对象取 status 或 state 字段递归判断', () => {
    expect(inferTone({ status: 'ok' })).toBe('ok')
    expect(inferTone({ state: 'error' })).toBe('down')
    expect(inferTone({ status: 'degraded' })).toBe('warn')
  })

  it('数字按是否有值判断，空值视为未就绪', () => {
    expect(inferTone(14)).toBe('ok')
    expect(inferTone(0)).toBe('idle')
    expect(inferTone(null)).toBe('idle')
    expect(inferTone(undefined)).toBe('idle')
  })

  it('数字与其字符串形态结论一致', () => {
    // 数字分支若单独存在会分叉出 ok/idle 两种结论；端点类型是 unknown，
    // 不能让结果取决于装箱形态
    expect(inferTone('14')).toBe(inferTone(14))
    expect(inferTone('0')).toBe(inferTone(0))
    expect(inferTone('3.4')).toBe(inferTone(3.4))
    expect(inferTone('14')).toBe('ok')
  })
})

describe('inferTone 与后端 /readyz 的实机契约', () => {
  // 后端 health.py 的每个检查项都是 {"ok": bool, ...}，状态键是 ok 而非 status。
  // 认不出这个键时，探活失败会走对象兜底分支返回 'ok' —— 控制台会为挂掉的数据库
  // 显示绿色"正常"，把本模块"不误报"的初衷做反。
  it('识别后端以 ok 作状态键的检查项', () => {
    expect(inferTone({ ok: true, postgis: '3.4.0' })).toBe('ok')
    expect(inferTone({ ok: true })).toBe('ok')
    expect(inferTone({ ok: false, error: 'OperationalError: boom' })).toBe('down')
  })

  it('无 ok 键但带错误信息的对象视为异常', () => {
    expect(inferTone({ detail: 'x', error: 'connection timeout' })).toBe('down')
    expect(inferTone({ exception: 'MilvusException' })).toBe('down')
    // 显式 null 的 error 不算失败
    expect(inferTone({ ok: true, error: null })).toBe('ok')
  })

  it('camelCase 异常名也能识别', () => {
    // 不拆词的话，'OperationalError' 里的 error 会被词边界漏掉
    expect(inferTone('OperationalError: connection refused')).toBe('down')
    expect(inferTone('ConnectionRefusedError')).toBe('down')
  })

  it('un- 前缀型否定不被其中的肯定词翻转', () => {
    // \b 对 'unhealthy' 这类前缀型构词不成立，会让否定整体失效
    expect(inferTone('unhealthy')).toBe('down')
    expect(inferTone('unready')).toBe('down')
    expect(inferTone('unloaded')).toBe('down')
  })

  it('短词只按词边界匹配，避免子串误判', () => {
    expect(inferTone('broken')).toBe('down') // 含 'ok'，但它不是独立词
    expect(inferTone('backup')).toBe('idle') // 含 'up'，但不是独立词
    expect(inferTone('support')).toBe('idle')
    expect(inferTone('ok')).toBe('ok')
  })

  it('download 不再被误判为 down', () => {
    expect(inferTone('download')).toBe('idle')
  })

  it('north 这类以 no 开头但非否定的词不被误判', () => {
    expect(inferTone('north')).toBe('idle')
  })
})

describe('formatValue', () => {
  it('布尔转为中文', () => {
    expect(formatValue(true)).toBe('是')
    expect(formatValue(false)).toBe('否')
  })

  it('数组只报条数', () => {
    expect(formatValue([1, 2, 3])).toBe('3 项')
    expect(formatValue([])).toBe('无')
  })

  it('对象优先展示可读字段', () => {
    expect(formatValue({ status: 'ok', extra: 1 })).toBe('ok')
    expect(formatValue({ model: 'bge-m3' })).toBe('bge-m3')
    expect(formatValue({ a: 1, b: 2 })).toBe('2 项')
  })

  it('空值用破折号', () => {
    expect(formatValue(null)).toBe('—')
    expect(formatValue(undefined)).toBe('—')
  })

  it('数字与字符串原样输出', () => {
    expect(formatValue(42)).toBe('42')
    expect(formatValue('cosyvoice')).toBe('cosyvoice')
  })

  it('失败原因必须露出，不能被压成计数', () => {
    // 否则 {"ok":false,"error":…} 只会显示"2 项"，运维看不到任何原因
    expect(formatValue({ ok: false, error: 'OperationalError: boom' })).toBe('OperationalError: boom')
  })

  it('成功时展示有信息量的字段而非计数', () => {
    expect(formatValue({ ok: true, postgis: '3.4.0' })).toBe('3.4.0')
    expect(formatValue({ ok: true, collections: ['wenlv_chunks'] })).toBe('wenlv_chunks')
    expect(formatValue({ ok: true, bucket: 'wenlv' })).toBe('wenlv')
  })

  it('只带状态键的对象不重复报计数', () => {
    expect(formatValue({ ok: true })).toBe('—')
  })

  it('超长错误信息被截断，避免撑破布局', () => {
    const long = `x${'y'.repeat(200)}`
    expect(formatValue({ error: long }).length).toBeLessThanOrEqual(61)
    expect(formatValue({ error: long }).endsWith('…')).toBe(true)
  })
})

describe('collectChecks', () => {
  // /readyz 顶层是 { work_order, stack, services }，不下钻一层就会把整个
  // services 塌成一行，四个组件状态全都看不见。
  it('从 services 子对象取出各组件检查项', () => {
    const ready = {
      work_order: '人工智能CV-AIGC-17',
      stack: { llm: 'Qwen' },
      services: { database: { ok: true }, redis: { ok: false, error: 'boom' } },
    }
    expect(collectChecks(ready)).toEqual([
      { name: 'database', value: { ok: true } },
      { name: 'redis', value: { ok: false, error: 'boom' } },
    ])
  })

  it('没有 services 时退回顶层，保证不返回空列表', () => {
    expect(collectChecks({ alpha: 1, beta: 2 })).toEqual([
      { name: 'alpha', value: 1 },
      { name: 'beta', value: 2 },
    ])
  })

  it('services 不是对象时也退回顶层', () => {
    expect(collectChecks({ services: 'n/a' })).toEqual([{ name: 'services', value: 'n/a' }])
  })
})
