/**
 * 工单16-20 延伸 · 平台化双端重构（批次 1）
 * 三态呈现：加载中 / 失败 / 空数据，由调用方提供成功态的渲染。
 *
 * 为什么统一收口：批次 0 的教训是"每个页面各自处理 loading 与 error"必然导致
 * 有的页面白屏、有的页面文案不一。这里把三态固定下来，页面只写业务渲染。
 */
import type { ReactNode } from 'react'
import type { AsyncState } from '../hooks/useAsync'

type Props<T> = {
  state: AsyncState<T>
  /** 成功态的渲染函数 */
  children: (data: T) => ReactNode
  /** 判空：返回 true 则显示空态而不是 children 的结果 */
  isEmpty?: (data: T) => boolean
  emptyText?: string
  loadingText?: string
  /** 失败时的重试入口（通常传 useAsync 的 reload） */
  onRetry?: () => void
  tone?: 'warm' | 'cool'
}

const TONE = {
  warm: {
    box: 'border-sand bg-surface/70',
    strong: 'text-ink',
    weak: 'text-ink-3',
    button: 'border-sand bg-surface text-ink-2 hover:border-amber/45 hover:text-amber-deep',
  },
  cool: {
    box: 'border-cool-line bg-cool-surface',
    strong: 'text-cool-ink',
    weak: 'text-cool-ink-3',
    button: 'border-cool-line bg-cool-surface text-cool-ink-2 hover:border-steel/40 hover:text-steel-deep',
  },
} as const

export default function StateView<T>({
  state,
  children,
  isEmpty,
  emptyText = '暂无数据',
  loadingText = '加载中…',
  onRetry,
  tone = 'warm',
}: Props<T>) {
  const skin = TONE[tone]

  if (state.kind === 'loading') {
    return (
      <div className={`rounded-2xl border border-dashed px-6 py-10 text-center text-[13px] ${skin.box} ${skin.weak}`}>
        {loadingText}
      </div>
    )
  }

  if (state.kind === 'error') {
    return (
      <div className="rounded-2xl border border-clay/40 bg-clay/10 px-5 py-4">
        <div className="text-[13px] text-clay-deep">加载失败：{state.message}</div>
        <div className="mt-1 text-[12px] text-clay">
          若为后端未就绪，请在 backend 目录启动 `python -m uvicorn app.main:app --port 8100`。
        </div>
        {onRetry && (
          <button onClick={onRetry} className={`mt-3 rounded-lg border px-3 py-1.5 text-[12.5px] ${skin.button}`}>
            重新加载
          </button>
        )}
      </div>
    )
  }

  if (isEmpty?.(state.data)) {
    return (
      <div className={`rounded-2xl border border-dashed px-6 py-10 text-center text-[13px] ${skin.box} ${skin.weak}`}>
        {emptyText}
      </div>
    )
  }

  return <>{children(state.data)}</>
}
