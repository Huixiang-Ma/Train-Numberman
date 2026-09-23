/**
 * 工单16-20 延伸 · 平台化双端重构（批次 0）
 * 空态 / 建设中提示。
 *
 * 批次 0 一次性建好双端路由表，尚未实现的模块用本组件渲染：
 * 它会显示模块名、工单依据与场景编号，因此导航可点、可验证，也不误导使用者。
 * 后续批次用真实页面替换 `readyRoutes.tsx` 中对应的映射。
 */
type Props = {
  title: string
  /** 对应工单条目 */
  ticket?: string
  /** 工单16 的功能场景编号 */
  scene?: string
  desc?: string
  tone?: 'warm' | 'cool'
}

const TONE = {
  warm: {
    box: 'border-sand bg-surface/70',
    title: 'text-ink',
    body: 'text-ink-3',
    tag: 'border-sand bg-surface-2 text-ink-3',
    glyph: 'text-amber-soft',
  },
  cool: {
    box: 'border-cool-line bg-cool-surface',
    title: 'text-cool-ink',
    body: 'text-cool-ink-3',
    tag: 'border-cool-line bg-cool-surface-2 text-cool-ink-3',
    glyph: 'text-steel-soft',
  },
} as const

export default function EmptyState({ title, ticket, scene, desc, tone = 'warm' }: Props) {
  const skin = TONE[tone]
  return (
    <div className={`rounded-2xl border border-dashed px-6 py-12 text-center ${skin.box}`}>
      <div className={`font-display text-2xl ${skin.glyph}`} aria-hidden>
        ◌
      </div>
      <div className={`mt-2 font-display text-[17px] ${skin.title}`}>{title}</div>
      {desc && <div className={`mx-auto mt-1 max-w-[520px] text-[13px] leading-relaxed ${skin.body}`}>{desc}</div>}
      {(ticket || scene) && (
        <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
          {ticket && <span className={`rounded-full border px-3 py-1 text-[11.5px] ${skin.tag}`}>依据 · {ticket}</span>}
          {scene && <span className={`rounded-full border px-3 py-1 text-[11.5px] ${skin.tag}`}>场景 · {scene}</span>}
          <span className={`rounded-full border px-3 py-1 text-[11.5px] ${skin.tag}`}>建设中</span>
        </div>
      )}
    </div>
  )
}
