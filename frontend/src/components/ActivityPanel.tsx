import { useCallback, useState } from 'react'
import { api, type ActivityRecommendItem, type GuideResult } from '../api/client'

/** 工单19 · 活动与体验创意推荐 + 参与攻略流程图（对应 /activity/recommend、/create/guide） */

const INTEREST_PRESETS = ['非遗', '美食', '亲子', '古建筑', '壁画', '夜游', '自然', '研学']

export default function ActivityPanel() {
  const [interests, setInterests] = useState<string[]>(['非遗', '美食'])
  const [items, setItems] = useState<ActivityRecommendItem[]>([])
  const [advice, setAdvice] = useState('')
  const [hasGeo, setHasGeo] = useState(false)
  const [guide, setGuide] = useState<GuideResult | null>(null)
  const [guideFor, setGuideFor] = useState('')
  const [loading, setLoading] = useState(false)
  const [guideLoading, setGuideLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const toggle = (value: string) =>
    setInterests((previous) =>
      previous.includes(value) ? previous.filter((item) => item !== value) : [...previous, value],
    )

  /** 带定位则按 PostGIS 距离排序；用户拒绝授权时后端退化为按兴趣排序 */
  const recommend = useCallback(async (withGeo: boolean) => {
    setLoading(true)
    setError(null)
    setGuide(null)
    try {
      let latitude: number | null = null
      let longitude: number | null = null
      if (withGeo && navigator.geolocation) {
        const position = await new Promise<GeolocationPosition>((resolve, reject) =>
          navigator.geolocation.getCurrentPosition(resolve, reject, { timeout: 8000 }),
        )
        latitude = position.coords.latitude
        longitude = position.coords.longitude
      }
      const data = await api.recommendActivity({ interests, latitude, longitude, limit: 5 })
      setItems(data.items)
      setAdvice(data.advice)
      setHasGeo(data.has_geo)
    } catch (exception) {
      setError((exception as Error).message)
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [interests])

  const buildGuide = async (item: ActivityRecommendItem) => {
    setGuideLoading(true)
    setError(null)
    setGuideFor(item.name)
    try {
      setGuide(await api.createGuide({ activity_id: item.id, interests }))
    } catch (exception) {
      setError((exception as Error).message)
      setGuide(null)
    } finally {
      setGuideLoading(false)
    }
  }

  return (
    <section className="rounded-2xl border border-sand bg-surface p-5 shadow-panel">
      <header className="mb-3 flex items-baseline justify-between gap-3">
        <h2 className="font-display text-base">活动与体验推荐</h2>
        <span className="text-[11.5px] text-ink-4">位置 + 兴趣 → 可参与活动与攻略</span>
      </header>

      <div className="mb-1.5 text-[11.5px] text-ink-4">兴趣标签</div>
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

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => recommend(true)}
          disabled={loading}
          className="rounded-full bg-amber px-4 py-2 text-[13px] text-[#FFF8EC] transition hover:bg-amber-deep disabled:opacity-50"
        >
          {loading ? '正在推荐…' : '按当前位置推荐'}
        </button>
        <button
          type="button"
          onClick={() => recommend(false)}
          disabled={loading}
          className="rounded-full border border-sand bg-surface px-4 py-2 text-[13px] text-ink-2 transition hover:border-amber hover:text-amber disabled:opacity-50"
        >
          仅按兴趣推荐
        </button>
      </div>

      {error && (
        <div className="mt-3 rounded-xl border border-clay/40 bg-clay/10 px-4 py-2.5 text-[12.5px] text-clay">{error}</div>
      )}

      {advice && (
        <div className="mt-3 rounded-xl border border-amber/30 bg-amber-soft/20 px-4 py-2.5 text-[12.5px] text-amber-deep">
          {advice}
          <span className="ml-2 text-[11px] text-amber-deep/70">{hasGeo ? '已按距离排序' : '未使用定位'}</span>
        </div>
      )}

      {items.length > 0 && (
        <ul className="mt-3 flex flex-col gap-2">
          {items.map((item) => (
            <li key={item.id} className="rounded-xl border border-sand bg-surface-2 px-3.5 py-2.5">
              <div className="flex flex-wrap items-baseline gap-2">
                <span className="text-[13.5px] text-ink">{item.name}</span>
                {item.attraction && <span className="text-[11.5px] text-ink-3">@{item.attraction}</span>}
                {item.distance_m !== null && (
                  <span className="text-[11.5px] text-amber-deep">距离约 {Math.round(item.distance_m)} 米</span>
                )}
                {item.match_score > 0 && <span className="text-[11.5px] text-ink-4">匹配 {item.match_score}</span>}
              </div>
              <div className="mt-1 text-[12px] text-ink-3">{item.schedule}</div>
              <div className="mt-0.5 text-[12px] text-ink-4">{item.description}</div>
              <button
                type="button"
                onClick={() => buildGuide(item)}
                disabled={guideLoading}
                className="mt-2 rounded-full border border-sand bg-surface px-3 py-1 text-[12px] text-ink-2 transition hover:border-amber hover:text-amber disabled:opacity-50"
              >
                {guideLoading && guideFor === item.name ? '正在生成攻略…' : '生成参与攻略与流程图'}
              </button>
            </li>
          ))}
        </ul>
      )}

      {guide && (
        <div className="mt-4 animate-rise rounded-xl border border-sand bg-surface-2 p-3.5">
          <div className="font-display text-[14.5px] text-ink">{guide.title}</div>
          <ol className="mt-2 flex flex-col gap-1">
            {guide.steps.map((step, index) => (
              <li key={`${index}-${step}`} className="text-[12.5px] text-ink-2">
                <span className="mr-1.5 text-amber-deep">{index + 1}.</span>
                {step}
              </li>
            ))}
          </ol>
          <div className="mt-2 text-[12.5px] leading-relaxed text-ink-3">{guide.guide_text}</div>
          {guide.diagram_url && (
            <div className="mt-3">
              <img src={guide.diagram_url} alt="参与流程图" className="w-full rounded-lg border border-sand" />
              <a
                href={guide.diagram_url}
                download
                className="mt-2 inline-block rounded-full border border-sand bg-surface px-3 py-1 text-[12px] text-ink-2 transition hover:border-amber hover:text-amber"
              >
                下载流程图
              </a>
            </div>
          )}
          {guide.mermaid && (
            <details className="mt-2">
              <summary className="cursor-pointer text-[11.5px] text-ink-4">查看 Mermaid 源码（可二次编辑）</summary>
              <pre className="mt-1.5 overflow-x-auto rounded-lg border border-sand bg-surface p-2.5 text-[11px] text-ink-3">
                {guide.mermaid}
              </pre>
            </details>
          )}
        </div>
      )}
    </section>
  )
}
