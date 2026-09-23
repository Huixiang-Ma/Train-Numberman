/**
 * docs/09 G3 · 下单深链 `/booking/:slotId`（批次 5）
 *
 * 为什么需要它：运营在推文、短信、二维码里发出去的链接往往只带一个时段 id
 * （例如"周五上午场余票告急，点这里直接订"）。没有这一层，深链只能落到首页，
 * 游客还得自己重新找景区、找票种、找时段，转发就白转了。
 *
 * 实现上是**薄壳**：反查出景区后把控制权交回 TicketPanel，
 * 下单流程只存在一份（TicketPanel），深链与正常入口不会走出两种行为。
 */
import { Link, useParams } from 'react-router-dom'
import { api } from '../../../api/client'
import PageHeader from '../../../shared/components/PageHeader'
import StateView from '../../../shared/components/StateView'
import { useAsync } from '../../../shared/hooks/useAsync'
import { yuan } from '../../../api/client'
import { TicketPanel } from './TicketPage'

export default function BookingPage() {
  const { slotId = '' } = useParams()
  const context = useAsync(() => api.slotContext(slotId), slotId)

  return (
    <StateView state={context.state} loadingText="正在还原下单信息…" onRetry={context.reload}>
      {(data) => {
        if (!data.park) {
          return (
            <div className="rounded-2xl border border-dashed border-sand bg-surface/70 px-6 py-10 text-center">
              <div className="font-display text-[16px] text-ink">该时段所属景区不可用</div>
              <p className="mt-1.5 text-[12.5px] text-ink-3">可能景区已被删除或时段已下线。</p>
              <Link
                to="/explore"
                className="mt-4 inline-block rounded-full border border-sand bg-surface px-4 py-1.5 text-[12.5px] text-ink-2"
              >
                去发现页看看
              </Link>
            </div>
          )
        }
        return (
          <div>
            {/* 深链来源提示：让游客知道自己从哪条链接进来、买的是哪一场 */}
            <PageHeader
              title="为你锁定这一场"
              desc={`${data.park.name} · ${data.ticket_type.name} · ${data.slot.slot_date} ${data.slot.start_time}–${data.slot.end_time} · ${yuan(
                data.ticket_type.price_cents,
              )}`}
              extra={
                <Link
                  to={`/tickets/${data.park.id}`}
                  className="rounded-full border border-sand bg-surface px-3 py-1.5 text-[12px] text-ink-3"
                >
                  查看其他场次
                </Link>
              }
            />
            <TicketPanel parkId={data.park.id} initialSlotId={slotId} />
          </div>
        )
      }}
    </StateView>
  )
}
