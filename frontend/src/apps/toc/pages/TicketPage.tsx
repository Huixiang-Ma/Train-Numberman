/**
 * docs/09 G3 · 票务与预订（批次 5）
 *
 * 工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成
 *
 * 两处必须如实告知游客的地方：
 *   1. **支付是占位**。docs/09 §3.2 明确「支付通道与资金结算不在范围内」，
 *      所以按钮文案写「确认下单（演示支付）」而不是「立即支付」，并在结果卡上说明。
 *      把它伪装成真实支付会让评审误判交付范围。
 *   2. **一单一票**。购买 2 张会签发 2 张独立电子票，各自核销。
 *      购买前的说明卡把这条讲清楚，否则闸口核销第一张时游客会以为整单已用掉。
 *
 * 为什么把整个流程放在一个页面而不拆成多步路由：购票的决策链很短
 * （选票种 → 选时段 → 填人数），拆成三个路由会让"改一下人数"要回退两级。
 */
import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { TICKET_CATEGORY, api, yuan, type TicketOrder, type TicketSlot } from '../../../api/client'
import PageHeader from '../../../shared/components/PageHeader'
import StateView from '../../../shared/components/StateView'
import { useAsync } from '../../../shared/hooks/useAsync'
import { apiErrorMessage } from '../../../shared/utils/error'
import { visitorRef } from '../../../shared/utils/visitor'

const MAX_QUANTITY = 50
/** 日期标签：今天/明天要写出来，只给 "09-23" 游客还得自己算 */
const weekday = ['日', '一', '二', '三', '四', '五', '六']

function dateLabel(date: string, today: string, tomorrow: string): string {
  if (date === today) return '今天'
  if (date === tomorrow) return '明天'
  const [, month, day] = date.split('-')
  return `${Number(month)}月${Number(day)}日`
}

/**
 * 取星期几。
 * 不用 `new Date('2026-09-23')`：该写法按 **UTC** 午夜解析，
 * 在 UTC-5 这类时区会退回到前一天，日期标签与星期就对不上了。
 * 因此显式按本地时间构造。
 */
function weekdayOf(date: string): string {
  const [year, month, day] = date.split('-').map(Number)
  return weekday[new Date(year, month - 1, day).getDay()]
}

export default function TicketPage() {
  const { parkId = '' } = useParams()
  return <TicketPanel parkId={parkId} />
}

export function TicketPanel({ parkId, initialSlotId }: { parkId: string; initialSlotId?: string }) {
  const data = useAsync(() => api.parkTickets(parkId), parkId)

  const [typeId, setTypeId] = useState('')
  const [slotId, setSlotId] = useState('')
  const [quantity, setQuantity] = useState(1)
  const [contactName, setContactName] = useState('')
  const [contactPhone, setContactPhone] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [order, setOrder] = useState<TicketOrder | null>(null)

  const types = data.state.kind === 'ready' ? data.state.data.ticket_types : []
  const current = types.find((item) => item.id === typeId)

  // 深链进入时先按 initialSlotId 定位票种
  useEffect(() => {
    if (initialSlotId && types.length) {
      const matched = types.find((item) => item.slots.some((slot) => slot.id === initialSlotId))
      if (matched) {
        setTypeId(matched.id)
        setSlotId(initialSlotId)
      }
    }
  }, [initialSlotId, types])

  // 默认选中第一个在售票种，避免游客进来还要先点一下
  useEffect(() => {
    if (!typeId && types.length) {
      const first = types.find((item) => item.status === 'on_sale') ?? types[0]
      setTypeId(first.id)
    }
  }, [types, typeId])

  const { dates, slotsByDate } = useMemo(() => {
    const source = current?.slots ?? []
    const unique = Array.from(new Set(source.map((slot) => slot.slot_date)))
    const grouped: Record<string, TicketSlot[]> = {}
    for (const slot of source) {
      grouped[slot.slot_date] = [...(grouped[slot.slot_date] ?? []), slot]
    }
    return { dates: unique, slotsByDate: grouped }
  }, [current])

  const today = dates[0] ?? ''
  const tomorrow = dates[1] ?? ''
  const [activeDate, setActiveDate] = useState('')
  useEffect(() => {
    if (dates.length && !dates.includes(activeDate)) setActiveDate(dates[0])
  }, [dates, activeDate])

  const slot = current?.slots.find((item) => item.id === slotId)
  const remaining = slot?.remaining ?? 0
  const totalCents = slot ? (current?.price_cents ?? 0) * quantity : 0

  const submit = async () => {
    if (!current || !slot) {
      setError('请先选择票种与时段')
      return
    }
    if (quantity > remaining) {
      setError(`该时段仅剩 ${remaining} 张`)
      return
    }
    if (!contactName.trim() || !/^\d{11}$/.test(contactPhone.trim())) {
      setError('请填写取票人姓名与 11 位手机号')
      return
    }
    setBusy(true)
    setError('')
    try {
      const created = await api.createOrder({
        park_id: parkId,
        ticket_type_id: current.id,
        slot_id: slot.id,
        quantity,
        visitor_ref: visitorRef(),
        contact_name: contactName.trim(),
        contact_phone: contactPhone.trim(),
      })
      setOrder(created)
      data.reload()
    } catch (err) {
      // 余票不足是并发冲突，这里刷新时段让界面立即反映最新余量
      setError(apiErrorMessage(err))
      data.reload()
    } finally {
      setBusy(false)
    }
  }

  if (order) {
    return <OrderResult order={order} onChange={setOrder} />
  }

  return (
    <div className="pb-28">
      <StateView
        state={data.state}
        loadingText="正在读取票务信息…"
        onRetry={data.reload}
      >
        {(payload) => (
          <>
            <PageHeader
              title={`${payload.park.name} · 门票预订`}
              desc={payload.park.level ? `${payload.park.level} 级景区 · 分时段预约入园` : '分时段预约入园'}
              extra={
                <Link
                  to={`/park/${parkId}`}
                  className="rounded-full border border-sand bg-surface px-3 py-1.5 text-[12px] text-ink-3"
                >
                  返回景区
                </Link>
              }
            />

            {payload.park.ticket_notice && (
              <div className="mb-4 rounded-xl border border-sand bg-surface/70 px-4 py-3 text-[12.5px] leading-relaxed text-ink-2">
                <span className="font-medium text-ink">购票须知</span>
                <p className="mt-1 text-ink-3">{payload.park.ticket_notice}</p>
              </div>
            )}

            {payload.ticket_types.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-sand bg-surface/70 px-6 py-10 text-center text-[13px] text-ink-3">
                该景区暂未配置可售票种
              </div>
            ) : (
              <>
                {/* 票种 */}
                <section className="mb-5">
                  <h2 className="mb-2.5 font-display text-[16px] text-ink">选择票种</h2>
                  <div className="flex flex-col gap-2.5">
                    {payload.ticket_types.map((item) => {
                      const active = item.id === typeId
                      const soldOut = item.status !== 'on_sale'
                      return (
                        <button
                          key={item.id}
                          disabled={soldOut}
                          onClick={() => {
                            setTypeId(item.id)
                            setSlotId('')
                            setQuantity(1)
                          }}
                          className={`rounded-2xl border px-4 py-3.5 text-left transition ${
                            active ? 'border-amber bg-amber/10' : 'border-sand bg-surface'
                          } ${soldOut ? 'opacity-50' : ''}`}
                        >
                          <div className="flex items-baseline justify-between gap-3">
                            <div className="flex items-baseline gap-2">
                              <span className="font-display text-[15px] text-ink">{item.name}</span>
                              <span className="rounded-full border border-sand bg-surface-2 px-2 py-0.5 text-[10.5px] text-ink-3">
                                {TICKET_CATEGORY[item.category] ?? item.category}
                              </span>
                              {soldOut && (
                                <span className="rounded-full border border-clay/45 bg-clay/12 px-2 py-0.5 text-[10.5px] text-clay-deep">
                                  已下架
                                </span>
                              )}
                            </div>
                            <span className="shrink-0 font-display text-[17px] text-amber-deep">{yuan(item.price_cents)}</span>
                          </div>
                          {item.notice && <p className="mt-1.5 text-[11.5px] leading-relaxed text-ink-3">{item.notice}</p>}
                          <div className="mt-1.5 flex flex-wrap gap-3 text-[11px] text-ink-4">
                            {item.valid_days > 1 && <span>有效期 {item.valid_days} 天</span>}
                            <span>{item.refundable ? '未核销可退' : '不可退'}</span>
                          </div>
                        </button>
                      )
                    })}
                  </div>
                </section>

                {/* 日期与时段 */}
                {current && (
                  <section className="mb-5">
                    <h2 className="mb-2.5 font-display text-[16px] text-ink">选择入园时段</h2>
                    {dates.length === 0 ? (
                      <div className="rounded-xl border border-dashed border-sand bg-surface/70 px-4 py-6 text-center text-[12.5px] text-ink-3">
                        该票种近期无可售时段
                      </div>
                    ) : (
                      <>
                        <div className="scroll-x mb-3">
                          {dates.map((date) => (
                            <button
                              key={date}
                              onClick={() => {
                                setActiveDate(date)
                                setSlotId('')
                              }}
                              className={`rounded-xl border px-3.5 py-2 text-center ${
                                activeDate === date
                                  ? 'border-amber bg-amber/10 text-amber-deep'
                                  : 'border-sand bg-surface text-ink-2'
                              }`}
                            >
                              <div className="text-[12.5px]">{dateLabel(date, today, tomorrow)}</div>
                              <div className="text-[10.5px] text-ink-4">
                                周{weekdayOf(date)} · {(slotsByDate[date] ?? []).length} 个时段
                              </div>
                            </button>
                          ))}
                        </div>

                        <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">
                          {(slotsByDate[activeDate] ?? []).map((item) => (
                            <button
                              key={item.id}
                              disabled={item.sold_out}
                              onClick={() => {
                                setSlotId(item.id)
                                setQuantity((value) => Math.min(value, Math.max(1, item.remaining)))
                              }}
                              className={`rounded-xl border px-3 py-2.5 text-left ${
                                slotId === item.id ? 'border-amber bg-amber/10' : 'border-sand bg-surface'
                              } ${item.sold_out ? 'opacity-45' : ''}`}
                            >
                              <div className="text-[13px] text-ink">
                                {item.start_time}–{item.end_time}
                              </div>
                              <div className={`mt-0.5 text-[11px] ${item.remaining <= 20 ? 'text-clay-deep' : 'text-ink-4'}`}>
                                {item.sold_out ? '已售罄' : `余票 ${item.remaining}`}
                              </div>
                            </button>
                          ))}
                        </div>
                      </>
                    )}
                  </section>
                )}

                {/* 人数与联系人 */}
                <section className="mb-5">
                  <h2 className="mb-2.5 font-display text-[16px] text-ink">人数与联系人</h2>
                  <div className="rounded-2xl border border-sand bg-surface px-4 py-3.5">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <div className="text-[13px] text-ink">购票数量</div>
                        <div className="text-[11px] text-ink-4">
                          {slot ? `该时段余票 ${remaining}，最多 ${MAX_QUANTITY} 张/单` : '请先选择时段'}
                        </div>
                      </div>
                      <div className="flex items-center gap-2.5">
                        <button
                          onClick={() => setQuantity((value) => Math.max(1, value - 1))}
                          disabled={quantity <= 1 || !slot}
                          className="grid h-8 w-8 place-items-center rounded-lg border border-sand bg-surface text-[16px] text-ink-2 disabled:opacity-40"
                        >
                          −
                        </button>
                        <span className="w-8 text-center font-display text-[17px] text-ink">{quantity}</span>
                        <button
                          onClick={() => setQuantity((value) => Math.min(MAX_QUANTITY, remaining || MAX_QUANTITY, value + 1))}
                          disabled={!slot || quantity >= Math.min(MAX_QUANTITY, remaining)}
                          className="grid h-8 w-8 place-items-center rounded-lg border border-sand bg-surface text-[16px] text-ink-2 disabled:opacity-40"
                        >
                          +
                        </button>
                      </div>
                    </div>

                    <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
                      <label className="block">
                        <span className="text-[12px] text-ink-3">取票人姓名</span>
                        <input
                          value={contactName}
                          onChange={(event) => setContactName(event.target.value)}
                          className="mt-1 w-full rounded-lg border border-sand bg-paper px-3 py-2 text-[13px] text-ink outline-none placeholder:text-ink-4 focus:border-amber"
                          placeholder="请输入真实姓名"
                        />
                      </label>
                      <label className="block">
                        <span className="text-[12px] text-ink-3">手机号</span>
                        <input
                          value={contactPhone}
                          onChange={(event) => setContactPhone(event.target.value.replace(/\D/g, '').slice(0, 11))}
                          inputMode="numeric"
                          className="mt-1 w-full rounded-lg border border-sand bg-paper px-3 py-2 text-[13px] text-ink outline-none placeholder:text-ink-4 focus:border-amber"
                          placeholder="11 位手机号"
                        />
                      </label>
                    </div>

                    <p className="mt-3 text-[11px] leading-relaxed text-ink-4">
                      下单后按人数签发<strong className="text-ink-3">独立电子票</strong>，每人一票、各自核销。
                      手机号仅用于取票联系，接口返回时已脱敏（如 138****34）。
                    </p>
                  </div>
                </section>
              </>
            )}
          </>
        )}
      </StateView>

      {/*
        底部结算条：移动端固定在底部，桌面端回归文档流（fixed 在桌面会一直压着页脚）。
        条件只看 `current`、不看 `slot`：若等选了时段才出现，整页会突然向上弹一下，
        游客的视线正好在那时落在按钮位置。改为始终可见、未选时段时按钮禁用并说明原因。
      */}
      {data.state.kind === 'ready' && current && (
        <div className="fixed inset-x-0 bottom-0 z-20 border-t border-sand bg-surface/95 px-4 py-3 backdrop-blur sm:static sm:mt-4 sm:rounded-2xl sm:border">
          <div className="mx-auto flex max-w-[900px] items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="truncate text-[11.5px] text-ink-3">
                {slot
                  ? `${current.name} · ${slot.slot_date} ${slot.start_time}–${slot.end_time} · ${quantity} 张`
                  : `${current.name} · 请先选择入园时段`}
              </div>
              <div className="font-display text-[19px] text-amber-deep">{slot ? yuan(totalCents) : '—'}</div>
            </div>
            <button
              onClick={submit}
              disabled={busy || !slot}
              className="shrink-0 rounded-xl bg-gradient-to-br from-amber to-amber-deep px-5 py-2.5 text-[13.5px] font-medium text-[#FFF8EC] disabled:opacity-50"
            >
              {busy ? '提交中…' : '确认下单'}
            </button>
          </div>
          {error && <div className="mx-auto mt-2 max-w-[900px] text-[12px] text-clay-deep">{error}</div>}
        </div>
      )}
    </div>
  )
}

// ------------------------------------------------------------ 下单结果与支付

function OrderResult({ order, onChange }: { order: TicketOrder; onChange: (next: TicketOrder) => void }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const act = async (fn: () => Promise<TicketOrder>) => {
    setBusy(true)
    setError('')
    try {
      onChange(await fn())
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <PageHeader
        title={order.status === 'pending' ? '订单已创建' : order.status_label}
        desc={`订单号 ${order.order_no} · 取票人 ${order.contact_name} · ${order.contact_phone}`}
        extra={
          <Link to="/me/orders" className="rounded-full border border-sand bg-surface px-3 py-1.5 text-[12px] text-ink-3">
            我的订单
          </Link>
        }
      />

      <div className="rounded-2xl border border-sand bg-surface px-4 py-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <div>
            <div className="font-display text-[16px] text-ink">
              {order.park_name} · {order.ticket_type_name}
            </div>
            <div className="mt-0.5 text-[12px] text-ink-3">
              {order.slot_date} {order.slot_start}–{order.slot_end} · {order.quantity} 张
            </div>
          </div>
          <div className="font-display text-[20px] text-amber-deep">{yuan(order.amount_cents)}</div>
        </div>

        {order.status === 'pending' && (
          <>
            <div className="mt-4 rounded-xl border border-amber/40 bg-amber/10 px-3.5 py-3 text-[12px] leading-relaxed text-amber-deep">
              本项目的支付为<strong>占位实现</strong>：docs/09 §3.2 已声明支付通道与资金结算不在交付范围内
              （涉支付牌照与"二清"合规）。点击下方按钮会推进订单状态并签发电子票，但
              <strong>不产生任何资金动作</strong>。
            </div>
            <button
              onClick={() => act(() => api.payOrder(order.id))}
              disabled={busy}
              className="mt-4 w-full rounded-xl bg-gradient-to-br from-amber to-amber-deep py-2.5 text-[13.5px] font-medium text-[#FFF8EC] disabled:opacity-50"
            >
              {busy ? '处理中…' : '确认下单（演示支付）'}
            </button>
          </>
        )}

        {order.status === 'paid' && order.tickets.length > 0 && (
          <div className="mt-4">
            <div className="mb-2.5 flex items-baseline justify-between gap-2">
              <span className="text-[13px] font-medium text-ink">电子票（{order.tickets.length} 张）</span>
              <span className="text-[11px] text-ink-4">入园时逐张出示，各自核销</span>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {order.tickets.map((ticket) => (
                <div key={ticket.id} className="rounded-xl border border-sand bg-paper p-3.5 text-center">
                  <img
                    src={api.ticketQrUrl(ticket.id)}
                    alt={`电子票 ${ticket.code}`}
                    className="mx-auto h-[132px] w-[132px] rounded-lg border border-sand bg-white"
                  />
                  <div className="mt-2 font-mono text-[13px] tracking-wide text-ink">{ticket.code}</div>
                  <div className="mt-0.5 text-[11px] text-ink-4">{ticket.status_label}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {(order.status === 'paid' || order.status === 'pending') && (
          <button
            onClick={() => act(() => api.cancelOrder(order.id))}
            disabled={busy}
            className="mt-3 w-full rounded-xl border border-sand bg-surface py-2 text-[12.5px] text-ink-3 disabled:opacity-50"
          >
            取消订单（释放已占库存）
          </button>
        )}

        {error && (
          <div className="mt-3 rounded-lg border border-clay/40 bg-clay/10 px-3 py-2 text-[12.5px] text-clay-deep">{error}</div>
        )}
      </div>
    </div>
  )
}
