/**
 * 工单19 §1 · ToC 个性化行程策划（S4）
 *
 * 行程面板本身复用既有 ItineraryPanel（工单19 的实现，不动其内部逻辑）；
 * 本页负责把它汇入 ToC 路由，并补上「行程 → 导览地图」这一步 ——
 * 后端 /create/map 按景点名回查 PostGIS 坐标出图，正好接在行程之后。
 */
import { useState } from 'react'
import { api, type CreationAsset, type ItineraryPlan } from '../../../api/client'
import ItineraryPanel from '../../../components/ItineraryPanel'

export default function PlanPage() {
  const [plan, setPlan] = useState<ItineraryPlan | null>(null)
  const [busy, setBusy] = useState(false)
  const [map, setMap] = useState<CreationAsset | null>(null)
  const [error, setError] = useState<string | null>(null)

  const generateMap = async () => {
    if (!plan?.stops.length) return
    setBusy(true)
    setError(null)
    try {
      const asset = await api.createMap({
        title: plan.title || '个性化导览地图',
        subtitle: plan.summary?.slice(0, 60) ?? '',
        stops: plan.stops.map((stop) => ({ name: stop.name, index: stop.index })),
      })
      setMap(asset)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <section className="rounded-2xl border border-sand bg-surface/70 px-5 py-4 shadow-panel">
        <h1 className="font-display text-[21px] leading-tight text-ink">个性化行程策划</h1>
        <p className="mt-1 text-[12.5px] leading-relaxed text-ink-3">
          按兴趣、时长、同行人与节奏生成专属线路；生成后可一键出导览地图。
        </p>
      </section>

      <ItineraryPanel onPlan={setPlan} />

      {plan && (
        <section className="rounded-2xl border border-sand bg-surface px-5 py-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="font-display text-[15px] text-ink">下一步</div>
              <p className="mt-0.5 text-[12px] text-ink-3">
                拿这条线路出导览地图（{plan.stops.length} 个站点，坐标由后端查 PostGIS 补齐）
              </p>
            </div>
            <button
              onClick={() => void generateMap()}
              disabled={busy}
              className="rounded-xl bg-gradient-to-br from-amber-soft to-amber-deep px-4 py-2 text-[13px] text-[#FFF8EC] disabled:opacity-50"
            >
              {busy ? '生成中…' : '生成导览地图'}
            </button>
          </div>

          {error && <div className="mt-2 rounded-xl border border-clay/40 bg-clay/10 px-3 py-2 text-[12.5px] text-clay-deep">{error}</div>}

          {map?.url && (
            <div className="mt-3 rounded-xl border border-sand bg-surface-2/50 px-3.5 py-3">
              <div className="text-[12.5px] text-ink-2">{map.title}</div>
              <img src={map.url} alt="导览地图" className="mt-2 w-full rounded-lg border border-sand" />
              <a href={map.url} download className="mt-2 inline-block rounded-lg border border-sand bg-surface px-3 py-1.5 text-[12.5px] text-ink-2">
                下载地图
              </a>
            </div>
          )}
        </section>
      )}
    </div>
  )
}
