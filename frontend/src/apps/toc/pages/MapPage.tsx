/**
 * 工单20 典型场景 13 · ToC 导览地图
 *
 * 地图由后端 /create/map 生成位图（坐标取自 PostGIS 真实景点数据），
 * 因此前端不需要任何地图 SDK（docs/08 §4.3 的既有决策）。
 * 本页是「已生成地图」的归档与下载入口；生成动作放在行程页，紧接行程生成之后。
 */
import { Link } from 'react-router-dom'
import { api } from '../../../api/client'
import StateView from '../../../shared/components/StateView'
import { useAsync } from '../../../shared/hooks/useAsync'

export default function MapPage() {
  const maps = useAsync(() => api.createAssets('map'), 'maps')

  return (
    <div className="flex flex-col gap-4">
      <section className="rounded-2xl border border-sand bg-surface/70 px-5 py-4 shadow-panel">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="font-display text-[21px] leading-tight text-ink">导览地图</h1>
            <p className="mt-1 text-[12.5px] leading-relaxed text-ink-3">
              按行程站点生成的个性化地图，可下载与打印。新地图在「行程」页生成后出现在这里。
            </p>
          </div>
          <Link to="/plan" className="rounded-xl bg-gradient-to-br from-amber-soft to-amber-deep px-4 py-2 text-[13px] text-[#FFF8EC]">
            去生成
          </Link>
        </div>
      </section>

      <StateView
        state={maps.state}
        tone="warm"
        loadingText="正在读取已生成的地图…"
        isEmpty={(data) => data.items.length === 0}
        emptyText="还没有导览地图。先去「行程」生成一条线路，再点「生成导览地图」。"
        onRetry={maps.reload}
      >
        {(data) => (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {data.items.map((item) => (
              <figure key={item.id} className="overflow-hidden rounded-2xl border border-sand bg-surface shadow-panel">
                {item.url ? (
                  <img src={item.url} alt={item.title || '导览地图'} className="w-full border-b border-sand" />
                ) : (
                  <div className="grid h-40 place-items-center border-b border-sand bg-surface-2 text-[12.5px] text-ink-4">
                    无预览
                  </div>
                )}
                <figcaption className="flex items-center justify-between gap-2 px-3.5 py-2.5">
                  <span className="min-w-0 truncate text-[12.5px] text-ink-2">{item.title || '导览地图'}</span>
                  {item.url && (
                    <a href={item.url} download className="shrink-0 rounded-lg border border-sand bg-surface px-2.5 py-1 text-[12px] text-ink-2">
                      下载
                    </a>
                  )}
                </figcaption>
              </figure>
            ))}
          </div>
        )}
      </StateView>
    </div>
  )
}
