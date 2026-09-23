/**
 * docs/09 G1 · ToC 景区详情页
 * 工单17 §2 结构化数据 + 工单16 §2.2 场景 S1/S6 的落地页。
 *
 * 设计取向：暖色沉浸，首屏是"景区身份"（名称/等级/状态/开放时间），
 * 往下依次是简介、票务须知、景点、活动，最后给出与数字人互动的入口。
 */
import { Link, useParams } from 'react-router-dom'
import { PARK_STATUS, api } from '../../../api/client'
import EmptyState from '../../../shared/components/EmptyState'
import StateView from '../../../shared/components/StateView'
import { useAsync } from '../../../shared/hooks/useAsync'
import { TONE_CLASS } from '../../../shared/utils/tone'

export default function ParkDetailPage() {
  const { id = '' } = useParams<{ id: string }>()
  const detail = useAsync(() => api.park(id), id)

  return (
    <StateView
      state={detail.state}
      tone="warm"
      loadingText="正在读取景区信息…"
      onRetry={detail.reload}
    >
      {(data) => {
        const status = PARK_STATUS[data.status]
        return (
          <div className="flex flex-col gap-5">
            {/* 首屏：景区身份 */}
            <section className="rounded-2xl border border-sand bg-surface/70 px-5 py-5 shadow-panel">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h1 className="font-display text-[24px] leading-tight text-ink">{data.name}</h1>
                    {data.level && (
                      <span className="rounded-full bg-amber/12 px-2.5 py-0.5 text-[11.5px] text-amber-deep">{data.level}</span>
                    )}
                    <span className={`rounded-full border px-2.5 py-0.5 text-[11px] ${TONE_CLASS[status?.tone ?? 'idle']}`}>
                      {status?.label ?? data.status}
                    </span>
                  </div>
                  <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-ink-3">
                    {data.destination && (
                      <span>
                        {data.destination.region} · {data.destination.name}
                      </span>
                    )}
                    <span>开放 {data.open_hours || '以现场公示为准'}</span>
                    <span>{data.attraction_count} 个景点</span>
                    {data.daily_capacity > 0 && <span>日承载 {data.daily_capacity.toLocaleString()} 人次</span>}
                  </div>
                </div>
                <Link
                  to="/guide"
                  className="rounded-xl bg-gradient-to-br from-amber-soft to-amber-deep px-4 py-2.5 text-[13px] text-[#FFF8EC]"
                >
                  和数字人聊聊这里
                </Link>
              </div>

              <p className="mt-3 text-[13.5px] leading-relaxed text-ink-2">{data.summary}</p>
              {data.description && (
                <p className="mt-2 text-[13px] leading-relaxed text-ink-3">{data.description}</p>
              )}

              {data.tags.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {data.tags.map((item) => (
                    <span key={item} className="rounded-full border border-sand bg-surface-2 px-2.5 py-0.5 text-[11px] text-ink-3">
                      {item}
                    </span>
                  ))}
                </div>
              )}
            </section>

            {/* 票务须知：票务模块属后续批次，这里如实说明而非假装可购 */}
            <section className="rounded-2xl border border-sand bg-surface px-5 py-4">
              <div className="mb-1.5 font-display text-[15px] text-ink">票务须知</div>
              <p className="text-[13px] leading-relaxed text-ink-2">
                {data.ticket_notice || '该景区暂未录入票务须知。'}
              </p>
              <div className="mt-2.5 rounded-xl border border-dashed border-sand bg-surface-2/60 px-3.5 py-2.5 text-[12px] text-ink-3">
                在线购票与预约时段属后续批次（docs/09 G3），当前仅展示须知。
              </div>
            </section>

            {/* 景点 */}
            <section>
              <div className="mb-3 font-display text-[16px] text-ink">景点（{data.attractions.length}）</div>
              {data.attractions.length === 0 ? (
                <EmptyState title="暂无景点" desc="该景区尚未录入景点，可在管理端补充。" ticket="docs/09 G2" />
              ) : (
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  {data.attractions.map((item) => (
                    <div key={item.id} className="rounded-2xl border border-sand bg-surface px-4 py-3.5">
                      <div className="font-display text-[15.5px] text-ink">{item.name}</div>
                      <p className="mt-1 text-[12.5px] leading-relaxed text-ink-2">{item.summary}</p>
                      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11.5px] text-ink-4">
                        {item.open_hours && <span>开放 {item.open_hours}</span>}
                        {item.tags.slice(0, 3).map((tag) => (
                          <span key={tag}>{tag}</span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>

            {/* 活动 */}
            {data.activities.length > 0 && (
              <section>
                <div className="mb-3 font-display text-[16px] text-ink">可参与活动（{data.activities.length}）</div>
                <div className="flex flex-col gap-3">
                  {data.activities.map((item) => (
                    <div key={item.id} className="rounded-2xl border border-sand bg-surface px-4 py-3.5">
                      <div className="flex flex-wrap items-baseline justify-between gap-2">
                        <span className="font-display text-[15.5px] text-ink">{item.name}</span>
                        <span className="text-[11.5px] text-ink-3">{item.schedule}</span>
                      </div>
                      <p className="mt-1 text-[12.5px] leading-relaxed text-ink-2">{item.description}</p>
                      {item.how_to_join && (
                        <p className="mt-1.5 text-[12px] text-ink-3">参与方式：{item.how_to_join}</p>
                      )}
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/*
              票务入口（docs/09 §4.1 要求景区详情含"票务入口"）。
              票务是这一页最强的行动意图，因此用主按钮而不是和其它入口同级的描边按钮。
            */}
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-amber/40 bg-amber/10 px-4 py-3.5">
              <div className="min-w-0">
                <div className="font-display text-[14.5px] text-ink">门票与预约</div>
                <p className="mt-0.5 text-[12px] leading-relaxed text-amber-deep">
                  分时段预约入园 · 未核销可退 · 一单一票，每人各自核销
                </p>
              </div>
              <Link
                to={`/tickets/${data.id}`}
                className="shrink-0 rounded-xl bg-gradient-to-br from-amber to-amber-deep px-4 py-2 text-[13px] font-medium text-[#FFF8EC]"
              >
                查看票价与场次
              </Link>
            </div>

            <div className="flex flex-wrap gap-2">
              <Link to="/explore" className="rounded-xl border border-sand bg-surface px-4 py-2 text-[12.5px] text-ink-2">
                返回发现
              </Link>
              <Link to="/plan" className="rounded-xl border border-sand bg-surface px-4 py-2 text-[12.5px] text-ink-2">
                让 AI 排一条线路
              </Link>
              <Link to="/activity" className="rounded-xl border border-sand bg-surface px-4 py-2 text-[12.5px] text-ink-2">
                看活动推荐
              </Link>
            </div>
          </div>
        )
      }}
    </StateView>
  )
}
