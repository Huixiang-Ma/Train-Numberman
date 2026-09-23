/**
 * docs/09 G3 · 票务大厅（批次 5）
 *
 * 底部 Tab 的「票务」需要一个落地页：点进来直接是某一个景区的购票页会很突兀
 * （游客还不知道有哪些景区在售），因此这一页先把"哪些景区能买、起价多少、
 * 今天还有没有票"摆出来，再进具体景区选场次。
 *
 * 为什么敢在这里并发拉取每个景区的票务：景区量级是**十位**（当前 5 个），
 * 并发 5 个请求换来"起价与今日余票"这一屏信息是划算的。若景区数上到百位，
 * 应改由后端提供一个聚合接口，而不是在前端扇出。
 */
import { Link } from 'react-router-dom'
import { TICKET_CATEGORY, api, yuan, type TicketType } from '../../../api/client'
import PageHeader from '../../../shared/components/PageHeader'
import StateView from '../../../shared/components/StateView'
import { useAsync } from '../../../shared/hooks/useAsync'

type ParkOffer = {
  id: string
  name: string
  level: string
  destinationName: string | null
  summary: string
  tickets: TicketType[]
  minPriceCents: number
  todayRemaining: number
  todaySlots: number
}

export default function TicketsHallPage() {
  const offers = useAsync(async () => {
    const parks = await api.parks({ limit: 100 })
    const detail = await Promise.all(
      parks.items.map(async (park) => {
        const payload = await api.parkTickets(park.id, 1).catch(() => null)
        const types = payload?.ticket_types ?? []
        // 起价取"在售票种"的最低值：含下架票种会报出一个买不到的价
        const onSale = types.filter((item) => item.status === 'on_sale')
        const prices = onSale.map((item) => item.price_cents)
        const todaySlots = onSale.reduce((sum, item) => sum + item.slots.length, 0)
        const todayRemaining = onSale.reduce(
          (sum, item) => sum + item.slots.reduce((inner, slot) => inner + slot.remaining, 0),
          0,
        )
        return {
          id: park.id,
          name: park.name,
          level: park.level,
          destinationName: park.destination_name,
          summary: park.summary,
          tickets: onSale,
          minPriceCents: prices.length ? Math.min(...prices) : 0,
          todayRemaining,
          todaySlots,
        } satisfies ParkOffer
      }),
    )
    return detail
  }, '')

  return (
    <div>
      <PageHeader
        title="门票预订"
        desc="分时段预约入园 · 未核销可退 · 支付为演示占位（docs/09 §3.2 已声明不含资金结算）"
        extra={
          <Link to="/me/orders" className="rounded-full border border-sand bg-surface px-3 py-1.5 text-[12px] text-ink-3">
            我的订单
          </Link>
        }
      />

      <StateView
        state={offers.state}
        loadingText="正在汇总各景区票务…"
        isEmpty={(data) => data.length === 0}
        emptyText="库中还没有景区，先由运营在控制台建档并配置票种"
        onRetry={offers.reload}
      >
        {(data) => (
          <div className="flex flex-col gap-3">
            <div className="text-[11.5px] text-ink-4">
              共 {data.length} 个景区可预订 · 余票为今日数据，实时以预订页为准
            </div>

            {data.map((park) => (
              <div key={park.id} className="rounded-2xl border border-sand bg-surface px-4 py-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-display text-[16px] text-ink">{park.name}</span>
                      {park.level && (
                        <span className="rounded-full border border-amber/45 bg-amber/10 px-2 py-0.5 text-[10.5px] text-amber-deep">
                          {park.level}
                        </span>
                      )}
                      {park.destinationName && (
                        <span className="text-[11px] text-ink-4">{park.destinationName}</span>
                      )}
                    </div>
                    {park.summary && (
                      <p className="mt-1 line-clamp-1 max-w-[560px] text-[12px] text-ink-3">{park.summary}</p>
                    )}
                  </div>

                  <div className="text-right">
                    {park.tickets.length === 0 ? (
                      <div className="text-[12.5px] text-ink-3">暂未开售</div>
                    ) : park.minPriceCents === 0 ? (
                      <div className="font-display text-[18px] text-amber-deep">免费预约</div>
                    ) : (
                      <div className="font-display text-[18px] text-amber-deep">
                        {yuan(park.minPriceCents)}
                        <span className="ml-1 text-[11px] text-ink-4">起</span>
                      </div>
                    )}
                    <div className="mt-0.5 text-[11px] text-ink-4">
                      {park.tickets.length > 0 ? `${park.todaySlots} 个今日时段` : '—'}
                    </div>
                  </div>
                </div>

                {park.tickets.length > 0 && (
                  <>
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {park.tickets.map((ticket) => (
                        <span
                          key={ticket.id}
                          className="rounded-full border border-sand bg-surface-2 px-2.5 py-1 text-[11px] text-ink-2"
                        >
                          {TICKET_CATEGORY[ticket.category] ?? ticket.category} {yuan(ticket.price_cents)}
                        </span>
                      ))}
                    </div>

                    <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-sand pt-3">
                      <span className="text-[11.5px] text-ink-4">
                        今日余票{' '}
                        <strong className={park.todayRemaining === 0 ? 'text-clay-deep' : 'text-ink-2'}>
                          {park.todayRemaining}
                        </strong>{' '}
                        张
                      </span>
                      <div className="flex gap-2">
                        <Link
                          to={`/park/${park.id}`}
                          className="rounded-full border border-sand bg-surface px-3.5 py-1.5 text-[12px] text-ink-3"
                        >
                          景区详情
                        </Link>
                        <Link
                          to={`/tickets/${park.id}`}
                          className="rounded-full bg-gradient-to-br from-amber to-amber-deep px-4 py-1.5 text-[12.5px] font-medium text-[#FFF8EC]"
                        >
                          选择场次购票
                        </Link>
                      </div>
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>
        )}
      </StateView>
    </div>
  )
}
