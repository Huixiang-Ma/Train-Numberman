/**
 * docs/09 G3 · 订单管理（批次 5）
 *
 * 三条如实告知写在界面上而不是藏进文档：
 *   1. **退款不含资金动作**。docs/09 §3.2 声明支付与结算不在范围内，
 *      这里的"退款"是状态流转与库存释放，不产生真实退款流水。
 *   2. **核销率的分母是已成交订单**，不含待支付。否则待支付订单一多，
 *      核销率会被稀释，运营会误判现场效率。
 *   3. **手机号已脱敏**（后端输出即 138****34），因为订单列表会被客服与运营共同查看。
 */
import { Fragment, useState } from 'react'
import { ORDER_TONE, api, yuan, type TicketOrder } from '../../../api/client'
import PageHeader from '../../../shared/components/PageHeader'
import StateView from '../../../shared/components/StateView'
import { useAsync } from '../../../shared/hooks/useAsync'
import { apiErrorMessage } from '../../../shared/utils/error'
import { TONE_CLASS } from '../../../shared/utils/tone'

const STATUS_OPTIONS = [
  { value: '', label: '全部状态' },
  { value: 'pending', label: '待支付' },
  { value: 'paid', label: '待使用' },
  { value: 'checked_in', label: '已核销' },
  { value: 'refunded', label: '已退款' },
  { value: 'cancelled', label: '已取消' },
]

export default function OrdersPage() {
  const [parkId, setParkId] = useState('')
  const [status, setStatus] = useState('')
  const [draft, setDraft] = useState('')
  const [keyword, setKeyword] = useState('')
  const [openId, setOpenId] = useState('')
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')

  const parks = useAsync(() => api.parks({ limit: 200 }), '')
  const orders = useAsync(
    () => api.adminOrders({ park_id: parkId || undefined, status: status || undefined, keyword: keyword || undefined, limit: 100 }),
    `${parkId}|${status}|${keyword}`,
  )
  const stats = useAsync(() => api.ticketStats(parkId || undefined), parkId)

  // 汇总与表格共用 parkId 作为 useAsync 的 key，切景区时两者一起重新取，
  // 不需要额外的 useEffect 同步（口径天然一致）。
  const reload = () => {
    orders.reload()
    stats.reload()
  }

  const flash = (message: string, isError = false) => {
    setNotice(isError ? '' : message)
    setError(isError ? message : '')
  }

  const refund = async (order: TicketOrder) => {
    const reason = window.prompt(`确认对订单 ${order.order_no} 退款？请填写原因（会记入订单）`, '运营审核通过')
    if (reason === null) return
    try {
      await api.refundOrder(order.id, reason)
      flash(`${order.order_no} 已退款，已占库存已释放（演示流程，未发生资金动作）`)
      reload()
    } catch (err) {
      flash(apiErrorMessage(err), true)
    }
  }

  return (
    <div>
      <PageHeader
        tone="cool"
        title="订单管理"
        desc="订单检索、状态跟踪与退款审核（docs/09 G3）· 退款为状态流转与库存释放，不含资金结算"
        extra={
          <button
            onClick={reload}
            className="rounded-lg border border-cool-line bg-cool-surface px-3 py-1.5 text-[12.5px] text-cool-ink-2 hover:border-steel/40 hover:text-steel-deep"
          >
            刷新
          </button>
        }
      />

      {notice && (
        <div className="mb-3 rounded-lg border border-steel/35 bg-steel/10 px-3.5 py-2 text-[12.5px] text-steel-deep">{notice}</div>
      )}
      {error && (
        <div className="mb-3 rounded-lg border border-clay/45 bg-clay/12 px-3.5 py-2 text-[12.5px] text-clay-deep">{error}</div>
      )}

      {/* 经营汇总 */}
      <StateView state={stats.state} tone="cool" loadingText="正在汇总…" onRetry={stats.reload}>
        {(data) => (
          <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
            {[
              { label: '订单总数', value: data.orders_total },
              { label: '待支付', value: data.orders_pending, tone: 'warn' as const },
              { label: '已成交', value: data.orders_paid },
              { label: '已核销', value: data.orders_checked_in },
              { label: '售票张数', value: data.tickets_sold },
              { label: '销售额', value: yuan(data.amount_cents) },
            ].map((item) => (
              <div key={item.label} className="rounded-xl border border-cool-line bg-cool-surface px-3.5 py-3 shadow-console">
                <div className="text-[11.5px] text-cool-ink-3">{item.label}</div>
                <div className={`mt-0.5 text-[19px] font-semibold ${item.tone === 'warn' ? 'text-amber-deep' : 'text-cool-ink'}`}>
                  {item.value}
                </div>
              </div>
            ))}
            <div className="col-span-2 rounded-xl border border-cool-line bg-cool-surface px-3.5 py-3 shadow-console sm:col-span-3 xl:col-span-6">
              <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-[11.5px] text-cool-ink-3">
                <span>
                  核销率 <strong className="text-[13px] text-cool-ink">{(data.checkin_rate * 100).toFixed(1)}%</strong>
                  <span className="ml-1 text-cool-ink-4">（分母为已成交订单 {data.orders_paid} 笔，不含待支付）</span>
                </span>
                <span>
                  已核销票券 {data.tickets_checked_in} / {data.tickets_sold} 张
                </span>
                <span>已退款 {data.orders_refunded} 笔</span>
              </div>
            </div>
          </div>
        )}
      </StateView>

      {/* 筛选 */}
      <div className="mb-4 flex flex-wrap items-center gap-2 rounded-xl border border-cool-line bg-cool-surface px-3.5 py-3 shadow-console">
        <form
          className="flex min-w-[200px] flex-1 gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            setKeyword(draft.trim())
          }}
        >
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="按订单号或取票人检索…"
            className="min-w-0 flex-1 rounded-lg border border-cool-line bg-cool-bg px-3 py-2 text-[12.5px] text-cool-ink outline-none placeholder:text-cool-ink-4 focus:border-steel/50"
          />
          <button type="submit" className="rounded-lg bg-steel px-3.5 py-2 text-[12.5px] text-white">
            搜索
          </button>
        </form>

        <label className="flex items-center gap-1.5 text-[12px] text-cool-ink-3">
          景区
          <select
            value={parkId}
            onChange={(event) => setParkId(event.target.value)}
            className="min-w-[150px] rounded-lg border border-cool-line bg-cool-bg px-2 py-2 text-[12.5px] text-cool-ink outline-none focus:border-steel/50"
          >
            <option value="">全部</option>
            {parks.state.kind === 'ready' &&
              parks.state.data.items.map((park) => (
                <option key={park.id} value={park.id}>
                  {park.name}
                </option>
              ))}
          </select>
        </label>

        <label className="flex items-center gap-1.5 text-[12px] text-cool-ink-3">
          状态
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value)}
            className="rounded-lg border border-cool-line bg-cool-bg px-2 py-2 text-[12.5px] text-cool-ink outline-none focus:border-steel/50"
          >
            {STATUS_OPTIONS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>

        {(keyword || parkId || status) && (
          <button
            onClick={() => {
              setDraft('')
              setKeyword('')
              setParkId('')
              setStatus('')
            }}
            className="rounded-lg border border-cool-line bg-cool-surface px-3 py-2 text-[12.5px] text-cool-ink-3"
          >
            重置
          </button>
        )}
      </div>

      <StateView
        state={orders.state}
        tone="cool"
        loadingText="正在读取订单…"
        isEmpty={(data) => data.items.length === 0}
        emptyText="没有匹配的订单"
        onRetry={orders.reload}
      >
        {(data) => (
          <div className="overflow-hidden rounded-xl border border-cool-line bg-cool-surface shadow-console">
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-[12.5px]">
                <thead>
                  <tr className="bg-cool-surface-2 text-left text-cool-ink-3">
                    <th className="px-3.5 py-2.5 font-medium">订单</th>
                    <th className="px-3.5 py-2.5 font-medium">票种 / 时段</th>
                    <th className="px-3.5 py-2.5 text-right font-medium">数量</th>
                    <th className="px-3.5 py-2.5 text-right font-medium">金额</th>
                    <th className="px-3.5 py-2.5 font-medium">取票人</th>
                    <th className="px-3.5 py-2.5 font-medium">状态</th>
                    <th className="px-3.5 py-2.5 text-right font-medium">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((order) => (
                    // Fragment 必须带 key：用 <> 简写在 map 中会触发 React 的 key 警告，
                    // 且警告不会导致报错，容易被长期忽略
                    <Fragment key={order.id}>
                      <tr className="border-t border-cool-line hover:bg-cool-surface-2/60">
                        <td className="px-3.5 py-2.5">
                          <div className="font-mono text-[11.5px] text-cool-ink">{order.order_no}</div>
                          <div className="mt-0.5 text-[11px] text-cool-ink-3">{order.park_name}</div>
                        </td>
                        <td className="px-3.5 py-2.5 text-cool-ink-2">
                          <div>{order.ticket_type_name}</div>
                          <div className="mt-0.5 text-[11px] text-cool-ink-3">
                            {order.slot_date} {order.slot_start}–{order.slot_end}
                          </div>
                        </td>
                        <td className="px-3.5 py-2.5 text-right text-cool-ink-2">{order.quantity}</td>
                        <td className="px-3.5 py-2.5 text-right text-cool-ink-2">{yuan(order.amount_cents)}</td>
                        <td className="px-3.5 py-2.5 text-cool-ink-2">
                          <div>{order.contact_name || '—'}</div>
                          <div className="mt-0.5 font-mono text-[11px] text-cool-ink-3">{order.contact_phone || '—'}</div>
                        </td>
                        <td className="px-3.5 py-2.5">
                          <span className={`rounded-full border px-2 py-0.5 text-[10.5px] ${TONE_CLASS[ORDER_TONE[order.status] ?? 'idle']}`}>
                            {order.status_label}
                          </span>
                        </td>
                        <td className="px-3.5 py-2.5 text-right">
                          <div className="flex justify-end gap-1.5">
                            {order.tickets.length > 0 && (
                              <button
                                onClick={() => setOpenId(openId === order.id ? '' : order.id)}
                                className="rounded-lg border border-cool-line bg-cool-surface px-2.5 py-1 text-[11.5px] text-cool-ink-2 hover:border-steel/40"
                              >
                                {openId === order.id ? '收起' : `电子票 ${order.tickets.length}`}
                              </button>
                            )}
                            {order.status === 'paid' && (
                              <button
                                onClick={() => refund(order)}
                                className="rounded-lg border border-clay/45 bg-clay/12 px-2.5 py-1 text-[11.5px] text-clay-deep"
                              >
                                退款
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                      {openId === order.id && (
                        <tr className="border-t border-cool-line bg-cool-bg">
                          <td colSpan={7} className="px-3.5 py-3">
                            <div className="flex flex-wrap gap-2">
                              {order.tickets.map((ticket) => (
                                <div key={ticket.id} className="rounded-lg border border-cool-line bg-cool-surface px-3 py-2">
                                  <div className="font-mono text-[11.5px] text-cool-ink">{ticket.code}</div>
                                  <div className="mt-1 flex items-center gap-2">
                                    <span
                                      className={`rounded-full border px-2 py-0.5 text-[10px] ${
                                        ticket.status === 'checked_in' ? TONE_CLASS.idle : TONE_CLASS.ok
                                      }`}
                                    >
                                      {ticket.status_label}
                                    </span>
                                    {ticket.gate && <span className="text-[10.5px] text-cool-ink-3">{ticket.gate}</span>}
                                    {ticket.checked_in_at && (
                                      <span className="text-[10.5px] text-cool-ink-4">
                                        {ticket.checked_in_at.replace('T', ' ').slice(5, 16)}
                                      </span>
                                    )}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </StateView>
    </div>
  )
}
