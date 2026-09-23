/**
 * 工单16-20 延伸 · 手写图表（批次 6）
 *
 * 为什么自己写而不引图表库：docs/08 §4.3 与 docs/09 §7.3 已明确「不引入图表库」。
 * 本批次需要的图形只有三种（横向条、纵向柱、折线），三种加起来不到 150 行，
 * 而任何图表库都会带来 40KB+ 与一套与手写工艺风格相冲突的默认样式。
 *
 * 三条实现纪律：
 *   1. **空数据不画图**。max 为 0 时直接渲染空态，否则会得到一条贴底的线或零高柱子，
 *      看起来像"数据是 0"而不是"没有数据"。
 *   2. **数值直接标出**。景区后台的使用者不是数据分析师，光看条长估不出数值。
 *   3. **配色只用已登记的语义色**（steel / amber / clay），不引入新色。
 */
import type { ReactNode } from 'react'

export type Datum = { label: string; value: number; hint?: string }

const EMPTY = '暂无数据'

function Empty({ text }: { text?: string }) {
  return (
    <div className="rounded-lg border border-dashed border-cool-line bg-cool-bg px-3 py-6 text-center text-[11.5px] text-cool-ink-3">
      {text ?? EMPTY}
    </div>
  )
}

/** 横向条形：适合标签较长的分类（票种名、意图名） */
export function BarList({
  data,
  unit = '',
  tone = 'steel',
  max: forcedMax,
}: {
  data: Datum[]
  unit?: string
  tone?: 'steel' | 'amber' | 'clay'
  max?: number
}) {
  if (!data.length) return <Empty />
  const max = Math.max(1, forcedMax ?? Math.max(...data.map((item) => item.value)))

  const fill = { steel: 'bg-steel', amber: 'bg-amber', clay: 'bg-clay' }[tone]

  return (
    <div className="flex flex-col gap-2">
      {data.map((item) => (
        <div key={item.label}>
          <div className="flex items-baseline justify-between gap-3 text-[11.5px]">
            <span className="truncate text-cool-ink-2" title={item.label}>
              {item.label}
            </span>
            <span className="shrink-0 tabular-nums text-cool-ink-3">
              {item.value.toLocaleString()}
              {unit}
              {item.hint && <span className="ml-1.5 text-cool-ink-4">{item.hint}</span>}
            </span>
          </div>
          <div className="mt-1 h-[7px] overflow-hidden rounded-full bg-cool-surface-2">
            {/* 宽度用百分比而不是固定像素：容器宽度随侧栏/窗口变化，固定像素会溢出 */}
            <div className={`h-full rounded-full ${fill}`} style={{ width: `${(item.value / max) * 100}%` }} />
          </div>
        </div>
      ))}
    </div>
  )
}

/** 纵向柱：适合有序的离散维度（核销小时分布） */
export function ColumnChart({ data, unit = '' }: { data: Datum[]; unit?: string }) {
  if (!data.length) return <Empty text="暂无核销记录" />
  const max = Math.max(1, ...data.map((item) => item.value))

  return (
    <div className="flex items-end gap-1.5 overflow-x-auto pb-1">
      {data.map((item) => (
        <div key={item.label} className="flex min-w-[34px] flex-1 flex-col items-center gap-1">
          <span className="text-[10.5px] tabular-nums text-cool-ink-3">
            {item.value}
            {unit}
          </span>
          <div className="flex h-[92px] w-full items-end rounded-md bg-cool-surface-2">
            <div
              className="w-full rounded-md bg-steel/70"
              // 最低 2px：值为 1 时也要看得见，否则和"没有"无法区分
              style={{ height: `${Math.max(2, (item.value / max) * 92)}px` }}
            />
          </div>
          <span className="text-[10.5px] text-cool-ink-4">{item.label}</span>
        </div>
      ))}
    </div>
  )
}

/** 折线：适合时间序列（近 N 天趋势） */
export function TrendLine({ data, unit = '' }: { data: Datum[]; unit?: string }) {
  if (data.length < 2) return <Empty text="数据点不足 2 个，无法成线" />

  const width = 640
  const height = 132
  const padX = 6
  const padY = 14
  const max = Math.max(1, ...data.map((item) => item.value))
  const step = (width - padX * 2) / (data.length - 1)

  const points = data.map((item, index) => ({
    x: padX + index * step,
    y: height - padY - (item.value / max) * (height - padY * 2),
    ...item,
  }))
  const line = points.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(' ')
  const area = `${padX},${height - padY} ${line} ${points[points.length - 1].x.toFixed(1)},${height - padY}`

  const labelStep = Math.max(1, Math.ceil(data.length / 6))

  return (
    <div>
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full" role="img" aria-label="趋势折线图">
        {[0, 0.5, 1].map((ratio) => (
          <line
            key={ratio}
            x1={padX}
            x2={width - padX}
            y1={padY + ratio * (height - padY * 2)}
            y2={padY + ratio * (height - padY * 2)}
            stroke="currentColor"
            className="text-cool-line"
            strokeWidth="1"
          />
        ))}
        <polygon points={area} className="fill-steel/12" />
        <polyline points={line} fill="none" strokeWidth="2" className="stroke-steel" strokeLinejoin="round" />
        {points.map((point) => (
          <circle key={point.label} cx={point.x} cy={point.y} r="2.6" className="fill-steel" />
        ))}
      </svg>
      <div className="mt-1 flex justify-between text-[10.5px] text-cool-ink-4">
        {data
          .filter((_, index) => index % labelStep === 0 || index === data.length - 1)
          .map((item) => (
            <span key={item.label}>{item.label}</span>
          ))}
      </div>
      <div className="mt-1 text-[10.5px] text-cool-ink-4">
        峰值 {max.toLocaleString()}
        {unit} · 共 {data.length} 个数据点
      </div>
    </div>
  )
}

/** 环形占比：用于"满足/待落实"这类二值汇总，比条形更省空间 */
export function RatioRing({ label, ratio, caption }: { label: string; ratio: number; caption?: ReactNode }) {
  const percent = Math.max(0, Math.min(1, ratio))
  const radius = 30
  const circumference = 2 * Math.PI * radius

  return (
    <div className="flex items-center gap-3">
      <svg viewBox="0 0 76 76" className="h-[76px] w-[76px] shrink-0" role="img" aria-label={`${label} ${(percent * 100).toFixed(1)}%`}>
        <circle cx="38" cy="38" r={radius} fill="none" strokeWidth="8" className="stroke-cool-surface-2" />
        <circle
          cx="38"
          cy="38"
          r={radius}
          fill="none"
          strokeWidth="8"
          strokeLinecap="round"
          className="stroke-steel"
          strokeDasharray={`${circumference * percent} ${circumference}`}
          // 从 12 点方向顺时针起画
          transform="rotate(-90 38 38)"
        />
        <text x="38" y="42" textAnchor="middle" className="fill-cool-ink text-[15px] font-semibold">
          {(percent * 100).toFixed(0)}%
        </text>
      </svg>
      <div className="min-w-0">
        <div className="text-[12.5px] font-medium text-cool-ink">{label}</div>
        {caption && <div className="mt-0.5 text-[11.5px] leading-relaxed text-cool-ink-3">{caption}</div>}
      </div>
    </div>
  )
}

/** 缺失数据源说明块：每个分析页都必须带，避免"模块空着"被误读成"数据为 0" */
export function GapNotice({ items }: { items: { item: string; reason: string }[] }) {
  if (!items.length) return null
  return (
    <section className="rounded-xl border border-amber/40 bg-amber/10 px-3.5 py-3">
      <div className="text-[12.5px] font-medium text-amber-deep">
        以下指标暂无数据源，因此本页不展示（不是数值为 0）
      </div>
      <ul className="mt-2 space-y-1.5">
        {items.map((gap) => (
          <li key={gap.item} className="text-[11.5px] leading-relaxed text-cool-ink-2">
            <span className="font-medium text-cool-ink">{gap.item}</span>
            <span className="text-cool-ink-3"> · {gap.reason}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}
