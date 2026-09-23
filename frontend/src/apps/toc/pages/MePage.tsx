/**
 * 工单19 §4 · ToC 我的（作品、订单与分享）
 *
 * 复用既有 SharePanel：它已经实现了"作品列表 → 生成分享 → 预览分享页"的完整闭环。
 * 批次 5 起订单与电子票已可用，入口指向 /me/orders —— 原先那句"属批次 5、尚未开放"
 * 的占位说明在批次 5 完成后就成了假话，必须一并改掉，否则界面会自我否定。
 */
import { Link } from 'react-router-dom'
import SharePanel from '../../../components/SharePanel'
import { useAsync } from '../../../shared/hooks/useAsync'
import { api, yuan } from '../../../api/client'
import { visitorRef } from '../../../shared/utils/visitor'

export default function MePage() {
  // 只取一屏概览所需的计数，不在这里铺开订单列表（那是 /me/orders 的职责）
  const orders = useAsync(() => api.myOrders(visitorRef()), '')
  const requests = useAsync(() => api.myServiceRequests(visitorRef()), '')

  const orderCount = orders.state.kind === 'ready' ? orders.state.data.total : null
  const pendingCount =
    orders.state.kind === 'ready' ? orders.state.data.items.filter((item) => item.status === 'pending').length : 0
  const validTickets =
    orders.state.kind === 'ready'
      ? orders.state.data.items.reduce(
          (sum, order) => sum + order.tickets.filter((ticket) => ticket.status === 'valid').length,
          0,
        )
      : 0
  const openRequests =
    requests.state.kind === 'ready' ? requests.state.data.items.filter((item) => item.status === 'open').length : 0

  return (
    <div className="flex flex-col gap-4">
      <section className="rounded-2xl border border-sand bg-surface/70 px-5 py-4 shadow-panel">
        <h1 className="font-display text-[21px] leading-tight text-ink">我的</h1>
        <p className="mt-1 text-[12.5px] leading-relaxed text-ink-3">
          这里是你生成过的内容（纪念图片、旅行短片、旅行日记、行程与导览地图）与已购门票的订单、电子票。
        </p>
      </section>

      {/* 票务概览 */}
      <section className="rounded-2xl border border-sand bg-surface/70 px-5 py-4 shadow-panel">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <div className="font-display text-[15px] text-ink">订单与电子票</div>
          <Link to="/me/orders" className="text-[12px] text-amber-deep underline">
            查看全部订单
          </Link>
        </div>

        {orderCount === null ? (
          <p className="mt-1.5 text-[12.5px] text-ink-3">正在读取订单…</p>
        ) : orderCount === 0 ? (
          <p className="mt-1.5 text-[12.5px] leading-relaxed text-ink-3">
            还没有订单。可以去票务大厅按景区挑票种与入园时段，下单后电子票会出现在这里。
          </p>
        ) : (
          <div className="mt-2.5 grid grid-cols-3 gap-2">
            {[
              { label: '订单总数', value: orderCount },
              { label: '待支付', value: pendingCount },
              { label: '可用电子票', value: validTickets },
            ].map((item) => (
              <div key={item.label} className="rounded-xl border border-sand bg-paper px-3 py-2.5 text-center">
                <div className="text-[11px] text-ink-3">{item.label}</div>
                <div className={`font-display text-[18px] ${item.label === '待支付' && item.value > 0 ? 'text-clay-deep' : 'text-ink'}`}>
                  {item.value}
                </div>
              </div>
            ))}
          </div>
        )}

        {orders.state.kind === 'ready' && orders.state.data.items[0] && (
          <p className="mt-2.5 text-[11.5px] text-ink-4">
            最近一笔：{orders.state.data.items[0].park_name} · {orders.state.data.items[0].ticket_type_name} ·{' '}
            {yuan(orders.state.data.items[0].amount_cents)}
          </p>
        )}
      </section>

      <SharePanel />

      {/* 反馈入口：/feedback 没有其它入链，这里必须给出，否则该页无法抵达 */}
      <section className="rounded-2xl border border-sand bg-surface/70 px-5 py-4 shadow-panel">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <div className="font-display text-[15px] text-ink">评价与反馈</div>
          <Link to="/feedback" className="text-[12px] text-amber-deep underline">
            去提交 / 查看
          </Link>
        </div>
        <p className="mt-1 text-[12.5px] leading-relaxed text-ink-3">
          咨询、投诉建议、失物招领与紧急求助都在这里提交，处理进度与景区回复同样在本页跟进。
          {openRequests > 0 && (
            <span className="ml-1 text-amber-deep">你有 {openRequests} 条工单尚待受理。</span>
          )}
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Link to="/tickets" className="rounded-xl border border-sand bg-surface px-3.5 py-2 text-[12.5px] text-ink-2">
            去票务大厅
          </Link>
          <Link to="/explore" className="rounded-xl border border-sand bg-surface px-3.5 py-2 text-[12.5px] text-ink-2">
            去发现景区
          </Link>
        </div>
      </section>
    </div>
  )
}
