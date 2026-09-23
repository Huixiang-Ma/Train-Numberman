/**
 * 工单16-20 延伸 · 平台化双端重构（批次 0）
 * 健康数据的容错解释。
 *
 * /readyz 与 /stack 返回 Record<string, unknown>，字段由后端演进决定。
 * 控制台不能把后端字段名写死，否则后端一改前端就白屏。
 * 因此这里只做「从任意取值推断状态」，新增检查项无需改前端。
 *
 * 两条硬规则（都来自实机契约，见 backend/app/api/v1/health.py）：
 *   1. 后端每个检查项用 `ok` 作状态键（不是 status/state）。认错这个键的后果
 *      是「数据库探活失败」被兜底成 'ok'，控制台显示绿色的"正常" —— 把这个
 *      模块"不误报"的初衷做反，所以 `ok` 必须优先识别。
 *   2. 匹配一律走**词边界**，并在否定词上 fail-closed（不确定就判异常）。
 *      朴素子串匹配会把 'broken' 里的 'ok' 认成正常、把 'download' 里的
 *      'down' 认成异常。
 */

// 状态语义色已提取到 ./tone（批次 1 的景区状态也需要同一套口径）。
// 这里既 import 到本地作用域（本文件的 inferTone 签名要用 Tone），又 re-export 给既有调用方。
import { TONE_CLASS, TONE_LABEL, type Tone } from './tone'

export { TONE_CLASS, TONE_LABEL, type Tone } from './tone'

const DOWN_WORDS = [
  'down',
  'fail',
  'error',
  'exception',
  'unavailable',
  'offline',
  'missing',
  'invalid',
  'timeout',
  'timed out',
  'broken',
  'unhealthy',
  'refused',
] as const

const WARN_WORDS = ['degraded', 'warn', 'warming', 'loading', 'pending', 'partial', 'slow'] as const

const OK_WORDS = ['ok', 'ready', 'healthy', 'available', 'loaded', 'up', 'pass'] as const

/**
 * 否定判定（fail-closed）。覆盖两种构词：
 *   - 分隔型：'not ready' / 'no data' / 'non-blocking'
 *   - 前缀型：'unhealthy' / 'unready' / 'unavailable'（un 后紧跟字母）
 * `\b` 不能用于前缀型 —— 'unhealthy' 里 `un` 后是字母，`\b` 不成立，
 * 会导致否定整体失效、'unhealthy' 被当成 'healthy' 报正常。
 */
const NEGATION = /^(?:no|not|non)\b|^un(?=[a-z])/

/** 把 camelCase / PascalCase 拆成小写词序列：'OperationalError' → 'operational error' */
const normalize = (text: string) => text.replace(/([a-z0-9])([A-Z])/g, '$1 $2').toLowerCase()

/** 词边界匹配：'broken' 不命中 'ok'，'download' 不命中 'down' */
function matchesWord(text: string, words: readonly string[]): boolean {
  return words.some((word) => new RegExp(`(?:^|[^a-z])${word}(?:[^a-z]|$)`).test(text))
}

export function inferTone(value: unknown): Tone {
  if (value === true) return 'ok'
  // 裸 false 语义不明（可能是"未启用"而非"故障"），故只降到待确认；
  // 而 { ok: false } 是明确的探活失败，见下面的对象分支。
  if (value === false) return 'warn'
  if (value === null || value === undefined) return 'idle'

  if (Array.isArray(value)) return value.length ? 'ok' : 'idle'

  if (typeof value === 'object') {
    const record = value as Record<string, unknown>
    // 规则 1：后端检查项的状态键是 `ok`
    if (typeof record.ok === 'boolean') return record.ok ? 'ok' : 'down'
    // 带错误信息的对象一律异常，避免其被兜底成正常
    if (record.error != null || record.exception != null) return 'down'
    const status = record.status ?? record.state
    if (status !== undefined) return inferTone(status)
    return 'ok'
  }

  const text = normalize(String(value)).trim()
  if (!text) return 'idle'
  // 数字与数字字符串走**同一条**判断：数字分支若单独存在，就会出现
  // inferTone(14) === 'ok' 而 inferTone('14') === 'idle' 的自相矛盾
  // （两个端点目前都不返回数字，但类型是 unknown，不能让结论取决于装箱形态）。
  if (/^-?\d+(?:\.\d+)?$/.test(text)) return Number(text) > 0 ? 'ok' : 'idle'
  if (NEGATION.test(text)) return 'down'
  if (matchesWord(text, DOWN_WORDS)) return 'down'
  if (matchesWord(text, WARN_WORDS)) return 'warn'
  if (matchesWord(text, OK_WORDS)) return 'ok'
  return 'idle'
}

/** 取值里最有信息量的字段，按优先级探测（纯启发式，与后端字段名解耦） */
const READABLE_KEYS = [
  'postgis',
  'version',
  'bucket',
  'collections',
  'model',
  'provider',
  'name',
  'status',
  'state',
  'mode',
  'llm',
  'embedding_model',
] as const

const truncate = (text: string, max = 60) => (text.length > max ? `${text.slice(0, max)}…` : text)

/** 把任意取值压成一行可读文本；对象优先暴露失败原因，其次暴露最有信息量的字段 */
export function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'number') return String(value)
  if (Array.isArray(value)) return value.length ? `${value.length} 项` : '无'
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>
    // 失败原因比任何计数都有用，必须优先露出（否则 {"ok":false,"error":…} 只会显示"2 项"）
    const error = record.error ?? record.exception ?? record.detail
    if (typeof error === 'string' && error) return truncate(error)
    for (const key of READABLE_KEYS) {
      const candidate = record[key]
      if (candidate === undefined || candidate === null) continue
      if (Array.isArray(candidate)) {
        if (candidate.length) return truncate(candidate.map(String).join('、'))
        continue
      }
      if (typeof candidate === 'object') continue
      return truncate(String(candidate))
    }
    // 只带状态键的对象（如 {"ok":true}）由状态标签承载语义，正文不必重复
    const rest = Object.keys(record).filter((key) => !['ok', 'error', 'exception', 'detail'].includes(key))
    return rest.length ? `${rest.length} 项` : '—'
  }
  return String(value)
}

export type HealthCheck = { name: string; value: unknown }

/**
 * 从 /readyz 响应中取出各组件检查项。
 *
 * 顶层形状是 { work_order, stack, services: { database, redis, milvus, minio } }，
 * 必须**下钻一层**：否则整个 services 会塌成一行，四个组件的状态一个都看不见，
 * 「组件健康」面板就成了摆设。
 */
export function collectChecks(ready: Record<string, unknown>): HealthCheck[] {
  const services = ready.services
  const source =
    services && typeof services === 'object' && !Array.isArray(services)
      ? (services as Record<string, unknown>)
      : ready
  return Object.entries(source).map(([name, value]) => ({ name, value }))
}


