/**
 * docs/09 G5 · 经营分析（批次 6）
 *
 * 页面结构按"运营打开后要回答的三个问题"组织，而不是按数据表：
 *   一、今天/这月卖得怎么样？      → 票务 KPI + 票种结构
 *   二、现场节奏对不对？            → 核销时段分布
 *   三、游客满不满意？              → 满意度 + 服务工单
 * 最后才是跨景区对比 —— 它是"通用多景区"相对"单景区"的直接增量价值。
 */
import { useState } from 'react'
import { TICKET_CATEGORY, api, yuan } from '../../../api/client'
import { BarList, ColumnChart, GapNotice, RatioRing, TrendLine } from '../../../shared/components/MiniChart'
import PageHeader from '../../../shared/components/PageHeader'
import StateView from '../../../shared/components/StateView'
import { useAsync } from '../../../shared/hooks/useAsync'

const DAY_OPTIONS = [7, 30, 90]

export default function AnalyticsPage() {
  const [parkId, setParkId] = useState('')
  const [days, setDays] = useState(30)

  const parks = useAsync(() => api.parks({ limit: 200 }), '')
  const business = useAsync(() => api.analyticsBusiness(parkId || undefined, days), `${parkId}|${days}`)
  const comparison = useAsync(() => api.analyticsParks(days), String(days))

  return (
    <div>
      <PageHeader
        tone="cool"
        title="经营分析"
        desc="票务、客流节奏、满意度与服务分布（docs/09 G5）· 需运营及以上角色"
        extra={
          <>
            <label className="flex items-center gap-1.5 text-[12px] text-cool-ink-3">
              景区
              <select
                value={parkId}
                onChange={(event) => setParkId(event.target.value)}
                className="min-w-[150px] rounded-lg border border-cool-line bg-cool-bg px-2 py-1.5 text-[12.5px] text-cool-ink outline-none focus:border-steel/50"
              >
                <option value="">全部景区</option>
                {parks.state.kind === 'ready' &&
                  parks.state.data.items.map((park) => (
                    <option key={park.id} value={park.id}>
                      {park.name}
                    </option>
                  ))}
              </select>
            </label>
            <div className="scroll-x">
              {DAY_OPTIONS.map((option) => (
                <button
                  key={option}
                  onClick={() => setDays(option)}
                  className={`rounded-full border px-3 py-1.5 text-[12px] ${
                    days === option
                      ? 'border-steel/45 bg-steel/10 font-medium text-steel-deep'
                      : 'border-cool-line bg-cool-surface-2 text-cool-ink-3'
                  }`}
                >
                  近 {option} 天
                </button>
              ))}
            </div>
            <button
              onClick={() => {
                business.reload()
                comparison.reload()
              }}
              className="rounded-lg border border-cool-line bg-cool-surface px-3 py-1.5 text-[12.5px] text-cool-ink-2 hover:border-steel/40 hover:text-steel-deep"
            >
              刷新
            </button>
          </>
        }
      />

      <StateView state={business.state} tone="cool" loadingText="正在汇总经营数据…" onRetry={business.reload}>
        {(data) => (
          <div className="flex flex-col gap-4">
            {/* 一、票务 */}
            <section>
              <h2 className="mb-2.5 text-[13px] font-medium text-cool-ink">票务</h2>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
                {[
                  { label: '订单总数', value: data.ticket.orders_total },
                  { label: '待支付', value: data.ticket.orders_pending, warn: true },
                  { label: '已成交', value: data.ticket.orders_paid },
                  { label: '已核销', value: data.ticket.orders_checked_in },
                  { label: '售票张数', value: data.ticket.tickets_sold },
                  { label: '销售额', value: yuan(data.ticket.amount_cents) },
                ].map((item) => (
                  <div key={item.label} className="rounded-xl border border-cool-line bg-cool-surface px-3.5 py-3 shadow-console">
                    <div className="text-[11.5px] text-cool-ink-3">{item.label}</div>
                    <div className={`mt-0.5 text-[19px] font-semibold ${item.warn ? 'text-amber-deep' : 'text-cool-ink'}`}>
                      {item.value}
                    </div>
                  </div>
                ))}
              </div>
              <p className="mt-2 text-[11px] leading-relaxed text-cool-ink-4">
                核销率 {(data.ticket.checkin_rate * 100).toFixed(1)}%（分母为已成交订单 {data.ticket.orders_paid} 笔，
                不含待支付）。销售额为<strong className="text-cool-ink-3">下单金额而非到账金额</strong>：
                支付为占位实现，不能用于财务对账。
              </p>
            </section>

            <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
              {/* 票种结构 */}
              <section className="rounded-xl border border-cool-line bg-cool-surface p-4 shadow-console">
                <h2 className="mb-3 text-[13px] font-medium text-cool-ink">票种销售结构</h2>
                <BarList
                  data={data.ticket_structure.map((item) => ({
                    label: `${item.name}（${TICKET_CATEGORY[item.category] ?? item.category}）`,
                    value: item.quantity,
                    hint: `${(item.share * 100).toFixed(1)}% · ${yuan(item.amount_cents)}`,
                  }))}
                  unit=" 张"
                />
              </section>

              {/* 核销时段 */}
              <section className="rounded-xl border border-cool-line bg-cool-surface p-4 shadow-console">
                <h2 className="mb-1 text-[13px] font-medium text-cool-ink">核销时段分布</h2>
                <p className="mb-3 text-[11px] leading-relaxed text-cool-ink-4">
                  按电子票核销时间统计。这是入园时段的<strong>代理指标</strong>，
                  不等于真实客流：免票儿童与旅游团通道不计入。
                </p>
                <ColumnChart
                  data={data.checkin_hours
                    .filter((item) => item.hour !== null)
                    .map((item) => ({ label: `${item.hour}时`, value: item.count }))}
                />
              </section>

              {/* 下单趋势 */}
              <section className="rounded-xl border border-cool-line bg-cool-surface p-4 shadow-console">
                <h2 className="mb-3 text-[13px] font-medium text-cool-ink">下单趋势（近 {data.days} 天）</h2>
                <TrendLine
                  data={data.order_trend.map((item) => ({ label: item.date.slice(5), value: item.orders, hint: `${item.tickets} 张` }))}
                  unit=" 单"
                />
              </section>

              {/* 满意度 */}
              <section className="rounded-xl border border-cool-line bg-cool-surface p-4 shadow-console">
                <h2 className="mb-3 text-[13px] font-medium text-cool-ink">游客满意度</h2>
                <RatioRing
                  label={`平均 ${data.review.average} 分 · 共 ${data.review.total} 条评价`}
                  ratio={data.review.average / 5}
                  caption="均分会掩盖分布差异：4.2 分可能来自「多数 5 分加少量 1 分」，也可能「全是 4 分」，对策完全不同。"
                />
                <div className="mt-3 border-t border-cool-line pt-3">
                  <BarList
                    data={Object.entries(data.review.distribution).map(([score, count]) => ({
                      label: `${score} 分`,
                      value: count,
                    }))}
                    unit=" 条"
                    tone="amber"
                  />
                </div>
              </section>
            </div>

            {/* 三、服务与内容 */}
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
              <section className="rounded-xl border border-cool-line bg-cool-surface p-4 shadow-console">
                <h2 className="mb-3 text-[13px] font-medium text-cool-ink">游客服务</h2>
                <div className="mb-3 grid grid-cols-3 gap-2 text-center">
                  {[
                    { label: '工单总数', value: data.service.total },
                    { label: '待受理', value: data.service.open },
                    { label: '加急', value: data.service.urgent_open, danger: true },
                  ].map((item) => (
                    <div key={item.label} className="rounded-lg border border-cool-line bg-cool-bg px-2 py-2">
                      <div className="text-[10.5px] text-cool-ink-3">{item.label}</div>
                      <div className={`text-[17px] font-semibold ${item.danger && item.value > 0 ? 'text-clay-deep' : 'text-cool-ink'}`}>
                        {item.value}
                      </div>
                    </div>
                  ))}
                </div>
                <BarList
                  data={[
                    { label: '咨询', value: data.service.by_category.consult ?? 0 },
                    { label: '投诉建议', value: data.service.by_category.complaint ?? 0 },
                    { label: '失物招领', value: data.service.by_category.lost ?? 0 },
                    { label: '紧急求助', value: data.service.by_category.help ?? 0 },
                  ]}
                  unit=" 条"
                />
                <p className="mt-2 text-[11px] text-cool-ink-4">
                  解决率 {(data.service.resolve_rate * 100).toFixed(1)}%
                  {data.service.avg_response_minutes != null && ` · 平均响应 ${data.service.avg_response_minutes} 分钟`}
                </p>
              </section>

              <section className="rounded-xl border border-cool-line bg-cool-surface p-4 shadow-console">
                <h2 className="mb-3 text-[13px] font-medium text-cool-ink">内容产量与传播</h2>
                <BarList
                  data={data.content.by_kind.map((item) => ({ label: item.kind, value: item.count }))}
                  unit=" 件"
                />
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <div className="rounded-lg border border-cool-line bg-cool-bg px-3 py-2">
                    <div className="text-[10.5px] text-cool-ink-3">产出合计</div>
                    <div className="text-[16px] font-semibold text-cool-ink">{data.content.total}</div>
                  </div>
                  <div className="rounded-lg border border-cool-line bg-cool-bg px-3 py-2">
                    <div className="text-[10.5px] text-cool-ink-3">分享访问</div>
                    <div className="text-[16px] font-semibold text-cool-ink">
                      {data.content.share_visits}
                      <span className="ml-1 text-[11px] font-normal text-cool-ink-4">
                        / {data.content.share_links} 链接
                      </span>
                    </div>
                  </div>
                </div>
              </section>

              <section className="rounded-xl border border-cool-line bg-cool-surface p-4 shadow-console">
                <h2 className="mb-3 text-[13px] font-medium text-cool-ink">跨景区对比（近 {data.days} 天）</h2>
                <StateView state={comparison.state} tone="cool" loadingText="正在对比…" onRetry={comparison.reload}>
                  {(rows) => (
                    <div className="overflow-x-auto">
                      <table className="w-full border-collapse text-[12px]">
                        <thead>
                          <tr className="text-left text-cool-ink-3">
                            <th className="py-1.5 pr-2 font-medium">景区</th>
                            <th className="py-1.5 pr-2 text-right font-medium">票数</th>
                            <th className="py-1.5 pr-2 text-right font-medium">销售额</th>
                            <th className="py-1.5 pr-2 text-right font-medium">核销率</th>
                            <th className="py-1.5 text-right font-medium">评分</th>
                          </tr>
                        </thead>
                        <tbody>
                          {rows.items.map((item) => (
                            <tr key={item.park_id} className="border-t border-cool-line">
                              <td className="py-1.5 pr-2">
                                <div className="flex items-center gap-1.5">
                                  <span className="truncate text-cool-ink-2">{item.park_name}</span>
                                  {item.level && (
                                    <span className="shrink-0 rounded border border-cool-line bg-cool-surface-2 px-1 text-[9.5px] text-cool-ink-3">
                                      {item.level}
                                    </span>
                                  )}
                                </div>
                              </td>
                              <td className="py-1.5 pr-2 text-right tabular-nums text-cool-ink-2">{item.tickets}</td>
                              <td className="py-1.5 pr-2 text-right tabular-nums text-cool-ink-2">
                                {yuan(item.amount_cents)}
                              </td>
                              <td className="py-1.5 pr-2 text-right tabular-nums text-cool-ink-2">
                                {item.orders > 0 ? `${(item.checkin_rate * 100).toFixed(0)}%` : '—'}
                              </td>
                              <td className="py-1.5 text-right tabular-nums text-cool-ink-2">
                                {item.rating ?? '—'}
                                {item.reviews > 0 && <span className="ml-0.5 text-[10px] text-cool-ink-4">({item.reviews})</span>}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </StateView>
              </section>
            </div>

            <GapNotice items={data.gaps} />
          </div>
        )}
      </StateView>
    </div>
  )
}
