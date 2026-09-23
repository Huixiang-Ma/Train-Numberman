/**
 * 工单16-20 延伸 · 平台化双端重构（批次 0）
 * 页面标题区（两端共用）。
 *
 * ToC 用宋体标题营造文化质感；ToB 用界面字体并收紧字号，避免控制台出现"海报感"。
 */
import type { ReactNode } from 'react'

type Props = {
  title: string
  desc?: string
  /** 右侧操作区 */
  extra?: ReactNode
  tone?: 'warm' | 'cool'
}

export default function PageHeader({ title, desc, extra, tone = 'warm' }: Props) {
  const warm = tone === 'warm'
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1
          className={
            warm
              ? 'font-display text-[21px] leading-tight text-ink'
              : 'text-[17px] font-semibold leading-tight text-cool-ink'
          }
        >
          {title}
        </h1>
        {desc && (
          <p className={`mt-1 text-[12.5px] leading-relaxed ${warm ? 'text-ink-3' : 'text-cool-ink-3'}`}>{desc}</p>
        )}
      </div>
      {extra && <div className="flex flex-wrap items-center gap-2">{extra}</div>}
    </div>
  )
}
