import type { PerceptionSocket } from '../hooks/usePerceptionSocket'

interface Props {
  socket: PerceptionSocket
}

/** 工单18 · 感知结果面板：检测/分类、手势、表情与互动建议 */
export default function PerceptionPanel({ socket }: Props) {
  const latest = socket.latest
  const data = latest?.data
  const providers = socket.providers

  // 分类（整图级标签）与检测（带位置框）分属两组数据，展示时合并为一条列表并标注来源，
  // 便于区分"整张图是什么"与"画面里在哪检出了什么"
  const sightings = [
    ...(data?.classification ?? []).map((item) => ({ label: item.label, score: item.score, kind: '分类' })),
    ...(data?.detections ?? []).map((item) => ({ label: item.label, score: item.score, kind: '检测' })),
  ].slice(0, 6)
  const gestures = data?.gestures ?? []
  const expression = data?.expression ?? null
  const suggestion = latest?.suggestion ?? null

  return (
    <section className="rounded-2xl border border-sand bg-surface p-5 shadow-panel">
      <header className="mb-3 flex items-baseline justify-between gap-3">
        <h2 className="font-display text-base">感知结果</h2>
        <span className="text-[11.5px] text-ink-4">
          {Object.keys(providers).length ? `${Object.keys(providers).length} 项能力在线` : '等待连接'}
        </span>
      </header>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <div className="mb-1.5 text-[11.5px] text-ink-4">检测 / 分类</div>
          <ul className="flex flex-col gap-1.5">
            {sightings.length === 0 && <li className="text-[12.5px] text-ink-4">未检出目标</li>}
            {sightings.map((item, index) => (
              <li
                key={`${item.kind}-${item.label}-${index}`}
                className="flex items-center justify-between rounded-lg border border-sand bg-surface-2 px-2.5 py-1.5 text-[12.5px] text-ink-2"
              >
                <span className="flex items-center gap-1.5">
                  <span className="rounded bg-amber-soft/50 px-1 py-px text-[10px] text-amber-deep">{item.kind}</span>
                  {item.label}
                </span>
                <span className="text-[11.5px] text-ink-3">{Math.round(item.score * 100)}%</span>
              </li>
            ))}
          </ul>
        </div>

        <div>
          <div className="mb-1.5 text-[11.5px] text-ink-4">手势 / 表情</div>
          <ul className="flex flex-col gap-1.5">
            {gestures.length === 0 && !expression && <li className="text-[12.5px] text-ink-4">未识别到手势</li>}
            {gestures.map((item, index) => (
              <li
                key={`${item.name}-${index}`}
                className="flex items-center justify-between rounded-lg border border-sand bg-surface-2 px-2.5 py-1.5 text-[12.5px] text-ink-2"
              >
                <span>{item.name}</span>
                <span className="text-[11.5px] text-ink-3">{Math.round(item.score * 100)}%</span>
              </li>
            ))}
            {expression && (
              <li className="flex items-center justify-between rounded-lg border border-sand bg-surface-2 px-2.5 py-1.5 text-[12.5px] text-ink-2">
                <span>表情 {expression.name}</span>
                <span className="text-[11.5px] text-ink-3">{Math.round(expression.score * 100)}%</span>
              </li>
            )}
          </ul>
        </div>
      </div>

      {suggestion && (
        <div className="mt-3 animate-rise rounded-xl border border-amber/30 bg-amber-soft/20 px-3.5 py-2.5 text-[13px] text-amber-deep">
          互动建议：{suggestion.text}（触发手势：{suggestion.gesture}）
        </div>
      )}

      {providers.detector && (
        <p className="mt-3 text-[11px] leading-relaxed text-ink-4">
          能力：{providers.detector} · {providers.gesture} · {providers.expression} · {providers.segmenter} · {providers.ocr}
        </p>
      )}
    </section>
  )
}
