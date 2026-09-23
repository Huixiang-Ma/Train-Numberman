import { useState } from 'react'
import { api, type ItineraryPlan } from '../api/client'

/** 工单19 · 个性化线路与活动创意生成（对应 POST /api/v1/itinerary/plan） */

const INTEREST_PRESETS = ['历史', '古建筑', '美食', '非遗', '亲子', '摄影', '自然', '壁画']
const DURATIONS = ['半日', '一日', '两日']
const COMPANIONS = ['独自', '亲子', '情侣', '长辈', '朋友']
const PACES = ['舒缓', '适中', '紧凑']

const KIND_LABEL: Record<string, string> = {
  sight: '参观',
  activity: '体验',
  food: '美食',
  rest: '休憩',
  photo: '拍照',
}

export default function ItineraryPanel({ onPlan }: { onPlan?: (plan: ItineraryPlan) => void }) {
  const [interests, setInterests] = useState<string[]>(['历史', '美食'])
  const [duration, setDuration] = useState('半日')
  const [companions, setCompanions] = useState('独自')
  const [pace, setPace] = useState('适中')
  const [plan, setPlan] = useState<ItineraryPlan | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const toggle = (value: string) =>
    setInterests((previous) =>
      previous.includes(value) ? previous.filter((item) => item !== value) : [...previous, value],
    )

  const generate = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.planItinerary({ interests, duration, companions, pace })
      setPlan(data)
      onPlan?.(data)
    } catch (exception) {
      setError((exception as Error).message)
      setPlan(null)
    } finally {
      setLoading(false)
    }
  }

  const download = () => {
    if (!plan) return
    const blob = new Blob([plan.route_text], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${plan.title}.txt`
    anchor.click()
    URL.revokeObjectURL(url)
  }

  return (
    <section className="rounded-2xl border border-sand bg-surface p-5 shadow-panel">
      <header className="mb-3 flex items-baseline justify-between gap-3">
        <h2 className="font-display text-base">个性化线路策划</h2>
        <span className="text-[11.5px] text-ink-4">兴趣 · 主题 · 时间 → 专属行程</span>
      </header>

      <div className="mb-1.5 text-[11.5px] text-ink-4">兴趣偏好</div>
      <div className="flex flex-wrap gap-1.5">
        {INTEREST_PRESETS.map((item) => {
          const active = interests.includes(item)
          return (
            <button
              key={item}
              type="button"
              onClick={() => toggle(item)}
              className={`rounded-full border px-3 py-1 text-[12.5px] transition ${
                active
                  ? 'border-amber bg-amber text-[#FFF8EC]'
                  : 'border-sand bg-surface-2 text-ink-2 hover:border-amber hover:text-amber'
              }`}
            >
              {item}
            </button>
          )
        })}
      </div>

      <div className="mt-4 grid grid-cols-3 gap-3">
        {[
          { label: '可用时长', value: duration, options: DURATIONS, set: setDuration },
          { label: '同行', value: companions, options: COMPANIONS, set: setCompanions },
          { label: '节奏', value: pace, options: PACES, set: setPace },
        ].map((group) => (
          <div key={group.label}>
            <div className="mb-1.5 text-[11.5px] text-ink-4">{group.label}</div>
            <div className="flex flex-wrap gap-1">
              {group.options.map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => group.set(option)}
                  className={`rounded-lg border px-2.5 py-1 text-[12px] transition ${
                    group.value === option
                      ? 'border-amber bg-amber-soft/40 text-amber-deep'
                      : 'border-sand bg-surface-2 text-ink-3 hover:border-amber'
                  }`}
                >
                  {option}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-4 flex items-center gap-2">
        <button
          type="button"
          onClick={generate}
          disabled={loading}
          className="rounded-full bg-amber px-4 py-2 text-[13px] text-[#FFF8EC] transition hover:bg-amber-deep disabled:opacity-50"
        >
          {loading ? '正在策划…' : '生成行程'}
        </button>
        {plan && (
          <button
            type="button"
            onClick={download}
            className="rounded-full border border-sand bg-surface px-4 py-2 text-[13px] text-ink-2 transition hover:border-amber hover:text-amber"
          >
            下载行程单
          </button>
        )}
      </div>

      {error && (
        <div className="mt-3 rounded-xl border border-clay/40 bg-clay/10 px-4 py-2.5 text-[12.5px] text-clay">{error}</div>
      )}

      {plan && (
        <div className="mt-4 animate-rise">
          <div className="font-display text-[15px] text-ink">{plan.title}</div>
          <div className="mt-0.5 text-[12.5px] leading-relaxed text-ink-3">{plan.summary}</div>

          <ol className="mt-3 flex flex-col gap-2">
            {plan.stops.map((stop) => (
              <li key={`${stop.index}-${stop.name}`} className="rounded-xl border border-sand bg-surface-2 px-3.5 py-2.5">
                <div className="flex items-baseline gap-2">
                  <span className="grid h-5 w-5 flex-none place-items-center rounded-full bg-amber text-[11px] text-[#FFF8EC]">
                    {stop.index}
                  </span>
                  <span className="text-[13.5px] text-ink">{stop.name}</span>
                  {stop.start_time && <span className="text-[11.5px] text-amber-deep">{stop.start_time}</span>}
                  <span className="text-[11.5px] text-ink-4">
                    {KIND_LABEL[stop.kind] ?? stop.kind}
                    {stop.duration ? ` · ${stop.duration}` : ''}
                  </span>
                </div>
                {stop.reason && <div className="mt-1 text-[12px] text-ink-3">为什么：{stop.reason}</div>}
                {stop.tips && <div className="mt-0.5 text-[12px] text-ink-4">提示：{stop.tips}</div>}
              </li>
            ))}
          </ol>

          <div className="mt-3 text-[11.5px] text-ink-4">
            生成链路：{plan.workflow}
            {plan.citations.length > 0 && ` · 引用 ${plan.citations.length} 条知识库资料`}
          </div>
        </div>
      )}
    </section>
  )
}
