/**
 * 工单16-20 延伸 · 平台化双端重构（批次 1）
 * 状态语义色：ok / warn / down / idle。
 *
 * 原先是 health.ts 的内部实现；批次 1 的景区营业状态也需要同一套口径，
 * 故提取为共享模块，避免两处各写一份配色而逐渐不一致。
 * health.ts 仍 re-export 这些符号，既有调用方无需改动。
 */

export type Tone = 'ok' | 'warn' | 'down' | 'idle'

/** 状态标签配色：ok/warn 落在两端共用的语义色上，down 用陶土色警示 */
export const TONE_CLASS: Record<Tone, string> = {
  ok: 'border-steel/35 bg-steel/10 text-steel-deep',
  warn: 'border-amber/40 bg-amber/10 text-amber-deep',
  down: 'border-clay/45 bg-clay/12 text-clay-deep',
  idle: 'border-cool-line bg-cool-surface-2 text-cool-ink-3',
}

export const TONE_LABEL: Record<Tone, string> = {
  ok: '正常',
  warn: '待确认',
  down: '异常',
  idle: '未就绪',
}
