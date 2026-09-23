/**
 * docs/09 G3 · 我的订单与电子票（批次 5）
 *
 * 一次请求取回订单及其电子票（后端 `_order_dict` 已聚合），不再逐单二次请求：
 * 电子票在核销前的核心用途是"当场出示二维码"，多一次往返就多一次现场卡住的机会。
 *
 * 「待使用」订单的电子票默认**折叠**：订单多时全展开会让页面被十几张二维码撑爆，
 * 而真正需要看码的时刻只有入园那一次。
 */
import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ORDER_TONE,
  TICKET_TONE,
  api,
  yuan,
  type ReviewItem,
  type TicketOrder,
} from '../../../api/client'
import PageHeader from '../../../shared/components/PageHeader'
import StateView from '../../../shared/components/StateView'
import { useAsync } from '../../../shared/hooks/useAsync'
import { apiErrorMessage } from '../../../shared/utils/error'
import { TONE_CLASS } from '../../../shared/utils/tone'
import { visitorRef } from '../../../shared/utils/visitor'

export default function MyOrdersPage() {
  const orders = useAsync(() => api.myOrders(visitorRef()), '')
  const [busyId, setBusyId] = useState('')
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')

  const act = async (id: string, fn: () => Promise<TicketOrder>, message: string) => {
    setBusyId(id)
    setError('')
    setNotice('')
    try {
      await fn()
      setNotice(message)
      orders.reload()
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setBusyId('')
    }
  }

  return (
    <div>
      <PageHeader
        title="我的订单"
        desc="订单、电子票与评价。本项目无游客账号，订单按本机匿名标识归集。"
        extra={
          <button
            onClick={orders.reload}
            className="rounded-full border border-sand bg-surface px-3 py-1.5 text-[12px] text-ink-3"
          >
            刷新
          </button>
        }
      />

      {notice && (
        <div className="mb-3 rounded-xl border border-amber/40 bg-amber/10 px-3.5 py-2 text-[12.5px] text-amber-deep">
          {notice}
        </div>
      )}
      {error && (
        <div className="mb-3 rounded-xl border border-clay/40 bg-clay/10 px-3.5 py-2 text-[12.5px] text-clay-deep">
          {error}
        </div>
      )}

      <StateView
        state={orders.state}
        loadingText="正在读取订单…"
        isEmpty={(data) => data.items.length === 0}
        emptyText="还没有订单。去发现页挑个景区，选好时段即可下单。"
        onRetry={orders.reload}
      >
        {(data) => (
          <div className="flex flex-col gap-3.5">
            {data.items.map((order) => (
              <OrderCard key={order.id} order={order} busy={busyId === order.id} onAct={act} onReviewed={orders.reload} />
            ))}
          </div>
        )}
      </StateView>
    </div>
  )
}

function OrderCard({
  order,
  busy,
  onAct,
  onReviewed,
}: {
  order: TicketOrder
  busy: boolean
  onAct: (id: string, fn: () => Promise<TicketOrder>, message: string) => Promise<void>
  onReviewed: () => void
}) {
  const [expanded, setExpanded] = useState(order.status === 'paid' && order.quantity === 1)
  const [reviewOpen, setReviewOpen] = useState(false)

  const canRefund = order.status === 'paid'
  const canReview = order.status === 'paid' || order.status === 'checked_in'

  return (
    <div className="rounded-2xl border border-sand bg-surface px-4 py-3.5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-display text-[15px] text-ink">{order.park_name}</span>
            <span className={`rounded-full border px-2 py-0.5 text-[10.5px] ${TONE_CLASS[ORDER_TONE[order.status] ?? 'idle']}`}>
              {order.status_label}
            </span>
          </div>
          <div className="mt-0.5 text-[12px] text-ink-3">
            {order.ticket_type_name} · {order.slot_date} {order.slot_start}–{order.slot_end} · {order.quantity} 张
          </div>
          <div className="mt-0.5 font-mono text-[11px] text-ink-4">{order.order_no}</div>
        </div>
        <div className="text-right">
          <div className="font-display text-[17px] text-amber-deep">{yuan(order.amount_cents)}</div>
          {order.payment_ref && <div className="text-[10.5px] text-ink-4">流水 {order.payment_ref.slice(0, 18)}…</div>}
        </div>
      </div>

      {/* 电子票 */}
      {order.tickets.length > 0 && (
        <div className="mt-3 border-t border-sand pt-3">
          <button
            onClick={() => setExpanded((value) => !value)}
            className="flex w-full items-center justify-between gap-2 text-left"
          >
            <span className="text-[12.5px] text-ink-2">
              电子票 {order.tickets.length} 张 · 已核销 {order.tickets.filter((item) => item.status === 'checked_in').length} 张
            </span>
            <span className="text-[11.5px] text-ink-4">{expanded ? '收起' : '展示二维码'}</span>
          </button>

          {expanded && (
            <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
              {order.tickets.map((ticket) => (
                <div key={ticket.id} className="rounded-xl border border-sand bg-paper p-3 text-center">
                  {ticket.status === 'valid' ? (
                    <img
                      src={api.ticketQrUrl(ticket.id)}
                      alt={`电子票 ${ticket.code}`}
                      className="mx-auto h-[112px] w-[112px] rounded-lg border border-sand bg-white"
                    />
                  ) : (
                    <div className="mx-auto grid h-[112px] w-[112px] place-items-center rounded-lg border border-dashed border-sand bg-surface-2 text-[11.5px] text-ink-4">
                      {ticket.status_label}
                    </div>
                  )}
                  <div className="mt-2 font-mono text-[11.5px] tracking-wide text-ink">{ticket.code}</div>
                  <span className={`mt-1 inline-block rounded-full border px-2 py-0.5 text-[10px] ${TONE_CLASS[TICKET_TONE[ticket.status] ?? 'idle']}`}>
                    {ticket.status_label}
                  </span>
                  {ticket.gate && <div className="mt-1 text-[10.5px] text-ink-4">{ticket.gate}</div>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 操作 */}
      {(order.status === 'pending' || canRefund || canReview) && (
        <div className="mt-3 flex flex-wrap gap-2 border-t border-sand pt-3">
          {order.status === 'pending' && (
            <>
              <button
                disabled={busy}
                onClick={() => onAct(order.id, () => api.payOrder(order.id), '已签发电子票（演示支付，未发生资金动作）')}
                className="rounded-full bg-gradient-to-br from-amber to-amber-deep px-4 py-1.5 text-[12.5px] font-medium text-[#FFF8EC] disabled:opacity-50"
              >
                确认下单（演示支付）
              </button>
              <button
                disabled={busy}
                onClick={() => onAct(order.id, () => api.cancelOrder(order.id), '订单已取消，已占库存已释放')}
                className="rounded-full border border-sand bg-surface px-4 py-1.5 text-[12.5px] text-ink-3 disabled:opacity-50"
              >
                取消订单
              </button>
            </>
          )}
          {canRefund && (
            <button
              disabled={busy}
              onClick={() => onAct(order.id, () => api.refundOrder(order.id, '游客自助申请'), '已退款（演示流程，未发生资金动作）')}
              className="rounded-full border border-sand bg-surface px-4 py-1.5 text-[12.5px] text-ink-3 disabled:opacity-50"
            >
              申请退款
            </button>
          )}
          {canReview && (
            <button
              onClick={() => setReviewOpen((value) => !value)}
              className="rounded-full border border-sand bg-surface px-4 py-1.5 text-[12.5px] text-ink-3"
            >
              {reviewOpen ? '收起评价' : '评价这次游玩'}
            </button>
          )}
          {order.status === 'refunded' && order.cancel_reason && (
            <span className="text-[11.5px] text-ink-4">退款原因：{order.cancel_reason}</span>
          )}
        </div>
      )}

      {reviewOpen && (
        <ReviewForm
          order={order}
          onDone={() => {
            setReviewOpen(false)
            onReviewed()
          }}
        />
      )}
    </div>
  )
}

/** 评价表单：一单一评，重复提交由后端覆盖（不会刷出多条） */
function ReviewForm({ order, onDone }: { order: TicketOrder; onDone: () => void }) {
  const [rating, setRating] = useState(5)
  const [content, setContent] = useState('')
  const [tags, setTags] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState<ReviewItem | null>(null)

  const OPTIONS = ['讲解好', '入园快', '环境美', '排队久', '值得再来']

  const submit = async () => {
    setBusy(true)
    setError('')
    try {
      const result = await api.createReview({
        park_id: order.park_id,
        order_id: order.id,
        visitor_ref: visitorRef(),
        rating,
        content: content.trim(),
        tags,
      })
      setSaved(result)
      onDone()
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mt-3 rounded-xl border border-sand bg-paper px-3.5 py-3">
      {saved ? (
        <div className="text-[12.5px] text-ink-2">评价已保存（{saved.rating} 分）。再次提交会覆盖这一次评价。</div>
      ) : (
        <>
          <div className="flex items-center gap-2">
            <span className="text-[12.5px] text-ink-2">评分</span>
            {[1, 2, 3, 4, 5].map((score) => (
              <button
                key={score}
                onClick={() => setRating(score)}
                className={`text-[19px] leading-none ${score <= rating ? 'text-amber' : 'text-ink-4'}`}
                aria-label={`${score} 分`}
              >
                ★
              </button>
            ))}
          </div>
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {OPTIONS.map((tag) => {
              const active = tags.includes(tag)
              return (
                <button
                  key={tag}
                  onClick={() => setTags((value) => (active ? value.filter((item) => item !== tag) : [...value, tag]))}
                  className={`rounded-full border px-2.5 py-1 text-[11.5px] ${
                    active ? 'border-amber bg-amber/10 text-amber-deep' : 'border-sand bg-surface text-ink-3'
                  }`}
                >
                  {tag}
                </button>
              )
            })}
          </div>
          <textarea
            value={content}
            onChange={(event) => setContent(event.target.value)}
            rows={3}
            placeholder="说说这次游玩的体验…"
            className="mt-2.5 w-full rounded-lg border border-sand bg-surface px-3 py-2 text-[12.5px] text-ink outline-none placeholder:text-ink-4 focus:border-amber"
          />
          {error && <div className="mt-2 text-[12px] text-clay-deep">{error}</div>}
          <button
            onClick={submit}
            disabled={busy}
            className="mt-2.5 rounded-full bg-gradient-to-br from-amber to-amber-deep px-4 py-1.5 text-[12.5px] font-medium text-[#FFF8EC] disabled:opacity-50"
          >
            {busy ? '提交中…' : '提交评价'}
          </button>
        </>
      )}
    </div>
  )
}
