/**
 * docs/09 G3 · 票种与时段库存（批次 5）
 *
 * 两个设计决定值得说明：
 *   1. **票种与时段同页、可展开**。运营的真实动作是"这个票种这周库存不够了"，
 *      票种与库存分两页会让人在两个页面之间反复跳。展开即见时段，改完留在原地。
 *   2. **库存下调有下限**。后端会拒绝把库存设到已售之下（否则会出现
 *      "已售 > 库存"的恒不可售脏状态），前端把这个下限**提前显示出来**，
 *      而不是让运营点了按钮才吃一个 409。
 */
import { useEffect, useState } from 'react'
import { TICKET_CATEGORY, api, yuan, type ParkTickets, type TicketType } from '../../../api/client'
import PageHeader from '../../../shared/components/PageHeader'
import StateView from '../../../shared/components/StateView'
import { useAsync } from '../../../shared/hooks/useAsync'
import { apiErrorMessage } from '../../../shared/utils/error'
import { TONE_CLASS } from '../../../shared/utils/tone'

export default function TicketsPage() {
  const [parkId, setParkId] = useState('')
  const [expanded, setExpanded] = useState('')
  const [creating, setCreating] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')

  const parks = useAsync(() => api.parks({ limit: 200 }), '')
  const detail = useAsync(() => (parkId ? api.parkTickets(parkId, 30) : Promise.resolve(null)), parkId)

  // 默认选第一个景区，避免运营进来先做一次无意义的选择
  useEffect(() => {
    if (!parkId && parks.state.kind === 'ready' && parks.state.data.items.length) {
      setParkId(parks.state.data.items[0].id)
    }
  }, [parks.state, parkId])

  const reload = () => detail.reload()

  const flash = (message: string, isError = false) => {
    setNotice(isError ? '' : message)
    setError(isError ? message : '')
  }

  return (
    <div>
      <PageHeader
        tone="cool"
        title="票种与时段库存"
        desc="按景区维护票种、价格与分时段库存（docs/09 G3）· 库存下调不得低于已售数量"
        extra={
          <>
            <button
              onClick={reload}
              className="rounded-lg border border-cool-line bg-cool-surface px-3 py-1.5 text-[12.5px] text-cool-ink-2 hover:border-steel/40 hover:text-steel-deep"
            >
              刷新
            </button>
            <button
              onClick={() => setCreating(true)}
              disabled={!parkId}
              className="rounded-lg bg-steel px-3.5 py-1.5 text-[12.5px] font-medium text-white disabled:opacity-45"
            >
              新建票种
            </button>
          </>
        }
      />

      {notice && (
        <div className="mb-3 rounded-lg border border-steel/35 bg-steel/10 px-3.5 py-2 text-[12.5px] text-steel-deep">
          {notice}
        </div>
      )}
      {error && (
        <div className="mb-3 rounded-lg border border-clay/45 bg-clay/12 px-3.5 py-2 text-[12.5px] text-clay-deep">
          {error}
        </div>
      )}

      <div className="mb-4 flex flex-wrap items-center gap-2 rounded-xl border border-cool-line bg-cool-surface px-3.5 py-3 shadow-console">
        <label className="flex items-center gap-2 text-[12px] text-cool-ink-3">
          景区
          <select
            value={parkId}
            onChange={(event) => {
              setParkId(event.target.value)
              setExpanded('')
            }}
            className="min-w-[180px] rounded-lg border border-cool-line bg-cool-bg px-2.5 py-2 text-[12.5px] text-cool-ink outline-none focus:border-steel/50"
          >
            {parks.state.kind === 'ready' &&
              parks.state.data.items.map((park) => (
                <option key={park.id} value={park.id}>
                  {park.name}
                  {park.level ? ` · ${park.level}` : ''}
                </option>
              ))}
          </select>
        </label>
        {detail.state.kind === 'ready' && detail.state.data && (
          <span className="text-[11.5px] text-cool-ink-4">
            售票种数 {detail.state.data.ticket_types.length} · 未来 {detail.state.data.days} 天
          </span>
        )}
      </div>

      {!parkId ? (
        <div className="rounded-xl border border-dashed border-cool-line bg-cool-surface px-4 py-10 text-center text-[13px] text-cool-ink-3">
          库中还没有景区。先在「景区与景点管理」补上景区，票种才有挂靠对象。
        </div>
      ) : (
        <StateView state={detail.state} tone="cool" loadingText="正在读取票种…" onRetry={reload}>
          {(payload) =>
            !payload ? null : payload.ticket_types.length === 0 ? (
              <div className="rounded-xl border border-dashed border-cool-line bg-cool-surface px-4 py-10 text-center text-[13px] text-cool-ink-3">
                该景区还没有票种。点右上角「新建票种」，可同时铺开未来若干天的时段。
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                {payload.ticket_types.map((item) => (
                  <TicketTypeRow
                    key={item.id}
                    item={item}
                    open={expanded === item.id}
                    onToggle={() => setExpanded(expanded === item.id ? '' : item.id)}
                    onChanged={reload}
                    onFlash={flash}
                  />
                ))}
              </div>
            )
          }
        </StateView>
      )}

      {creating && parkId && (
        <CreateTypeDrawer
          parkId={parkId}
          onClose={() => setCreating(false)}
          onDone={(message) => {
            setCreating(false)
            flash(message)
            reload()
          }}
        />
      )}
    </div>
  )
}

function TicketTypeRow({
  item,
  open,
  onToggle,
  onChanged,
  onFlash,
}: {
  item: ParkTickets['ticket_types'][number]
  open: boolean
  onToggle: () => void
  onChanged: () => void
  onFlash: (message: string, isError?: boolean) => void
}) {
  const [priceYuan, setPriceYuan] = useState((item.price_cents / 100).toFixed(2))
  const [busy, setBusy] = useState(false)

  const totalInventory = item.slots.reduce((sum, slot) => sum + slot.inventory, 0)
  const totalSold = item.slots.reduce((sum, slot) => sum + slot.sold, 0)
  const onSale = item.status === 'on_sale'

  const save = async () => {
    const cents = Math.round(Number(priceYuan) * 100)
    if (!Number.isFinite(cents) || cents < 0) {
      onFlash('价格需为非负数字', true)
      return
    }
    setBusy(true)
    try {
      await api.updateTicketType(item.id, { price_cents: cents })
      onFlash(`「${item.name}」价格已更新为 ${yuan(cents)}`)
      onChanged()
    } catch (err) {
      onFlash(apiErrorMessage(err), true)
    } finally {
      setBusy(false)
    }
  }

  const toggleStatus = async () => {
    setBusy(true)
    try {
      await api.updateTicketType(item.id, { status: onSale ? 'off_shelf' : 'on_sale' })
      onFlash(`「${item.name}」已${onSale ? '下架' : '上架'}`)
      onChanged()
    } catch (err) {
      onFlash(apiErrorMessage(err), true)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="overflow-hidden rounded-xl border border-cool-line bg-cool-surface shadow-console">
      <div className="flex flex-wrap items-center gap-3 px-3.5 py-3">
        <button onClick={onToggle} className="flex min-w-0 flex-1 items-center gap-2 text-left">
          <span className="text-[12px] text-cool-ink-4">{open ? '▾' : '▸'}</span>
          <span className="font-medium text-cool-ink">{item.name}</span>
          <span className="rounded-full border border-cool-line bg-cool-surface-2 px-2 py-0.5 text-[10.5px] text-cool-ink-3">
            {TICKET_CATEGORY[item.category] ?? item.category}
          </span>
          <span className={`rounded-full border px-2 py-0.5 text-[10.5px] ${onSale ? TONE_CLASS.ok : TONE_CLASS.idle}`}>
            {onSale ? '在售' : '已下架'}
          </span>
          {item.valid_days > 1 && (
            <span className="text-[10.5px] text-cool-ink-4">有效期 {item.valid_days} 天</span>
          )}
        </button>

        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11.5px] text-cool-ink-3">
            总量 {totalInventory} · 已售 {totalSold} · 余票{' '}
            <span className={totalInventory - totalSold <= 0 ? 'text-clay-deep' : 'text-cool-ink-2'}>
              {totalInventory - totalSold}
            </span>
          </span>
          <label className="flex items-center gap-1.5 text-[11.5px] text-cool-ink-3">
            单价 ¥
            <input
              value={priceYuan}
              onChange={(event) => setPriceYuan(event.target.value)}
              inputMode="decimal"
              className="w-[78px] rounded-lg border border-cool-line bg-cool-bg px-2 py-1.5 text-[12.5px] text-cool-ink outline-none focus:border-steel/50"
            />
          </label>
          <button
            onClick={save}
            disabled={busy}
            className="rounded-lg bg-steel px-2.5 py-1.5 text-[11.5px] text-white disabled:opacity-50"
          >
            保存价格
          </button>
          <button
            onClick={toggleStatus}
            disabled={busy}
            className="rounded-lg border border-cool-line bg-cool-surface px-2.5 py-1.5 text-[11.5px] text-cool-ink-2 hover:border-steel/40 disabled:opacity-50"
          >
            {onSale ? '下架' : '上架'}
          </button>
        </div>
      </div>

      {open && (
        <div className="border-t border-cool-line">
          {item.slots.length === 0 ? (
            <div className="px-3.5 py-6 text-center text-[12.5px] text-cool-ink-3">该票种近期没有时段</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-[12.5px]">
                <thead>
                  <tr className="bg-cool-surface-2 text-left text-cool-ink-3">
                    <th className="px-3.5 py-2 font-medium">日期</th>
                    <th className="px-3.5 py-2 font-medium">时段</th>
                    <th className="px-3.5 py-2 text-right font-medium">已售</th>
                    <th className="px-3.5 py-2 text-right font-medium">余票</th>
                    <th className="px-3.5 py-2 font-medium">库存上限</th>
                  </tr>
                </thead>
                <tbody>
                  {item.slots.map((slot) => (
                    <SlotRow key={slot.id} slot={slot} onChanged={onChanged} onFlash={onFlash} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function SlotRow({
  slot,
  onChanged,
  onFlash,
}: {
  slot: ParkTickets['ticket_types'][number]['slots'][number]
  onChanged: () => void
  onFlash: (message: string, isError?: boolean) => void
}) {
  const [value, setValue] = useState(String(slot.inventory))
  const [busy, setBusy] = useState(false)

  const save = async () => {
    const next = Number(value)
    if (!Number.isInteger(next) || next < 0) {
      onFlash('库存需为非负整数', true)
      return
    }
    // 提前拦住"低于已售"的情况：后端也会拒，但让运营在这里就看到下限更省事
    if (next < slot.sold) {
      onFlash(`该时段已售 ${slot.sold} 张，库存不能低于此值`, true)
      return
    }
    setBusy(true)
    try {
      await api.updateSlot(slot.id, next)
      onFlash(`${slot.slot_date} ${slot.start_time} 库存已设为 ${next}`)
      onChanged()
    } catch (err) {
      onFlash(apiErrorMessage(err), true)
    } finally {
      setBusy(false)
    }
  }

  return (
    <tr className="border-t border-cool-line">
      <td className="px-3.5 py-2 text-cool-ink-2">{slot.slot_date}</td>
      <td className="px-3.5 py-2 text-cool-ink-2">
        {slot.start_time}–{slot.end_time}
      </td>
      <td className="px-3.5 py-2 text-right text-cool-ink-2">{slot.sold}</td>
      <td className={`px-3.5 py-2 text-right ${slot.sold_out ? 'text-clay-deep' : 'text-cool-ink-2'}`}>
        {slot.remaining}
        {slot.sold_out && <span className="ml-1.5 text-[10.5px]">已售罄</span>}
      </td>
      <td className="px-3.5 py-2">
        <div className="flex items-center gap-1.5">
          <input
            value={value}
            onChange={(event) => setValue(event.target.value)}
            inputMode="numeric"
            className="w-[84px] rounded-lg border border-cool-line bg-cool-bg px-2 py-1 text-[12px] text-cool-ink outline-none focus:border-steel/50"
          />
          <button
            onClick={save}
            disabled={busy || value === String(slot.inventory)}
            className="rounded-lg border border-cool-line bg-cool-surface px-2 py-1 text-[11px] text-cool-ink-2 hover:border-steel/40 disabled:opacity-40"
          >
            保存
          </button>
          <span className="text-[10.5px] text-cool-ink-4">下限 {slot.sold}</span>
        </div>
      </td>
    </tr>
  )
}

function CreateTypeDrawer({
  parkId,
  onClose,
  onDone,
}: {
  parkId: string
  onClose: () => void
  onDone: (message: string) => void
}) {
  const [name, setName] = useState('')
  const [category, setCategory] = useState('adult')
  const [priceYuan, setPriceYuan] = useState('')
  const [notice, setNotice] = useState('')
  const [validDays, setValidDays] = useState('1')
  const [totalDays, setTotalDays] = useState('7')
  const [dailyInventory, setDailyInventory] = useState('200')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const submit = async () => {
    if (!name.trim()) {
      setError('请填写票种名称')
      return
    }
    const cents = Math.round(Number(priceYuan || '0') * 100)
    if (!Number.isFinite(cents) || cents < 0) {
      setError('价格需为非负数字')
      return
    }
    setBusy(true)
    setError('')
    try {
      const created: TicketType = await api.createTicketType({
        park_id: parkId,
        name: name.trim(),
        category,
        price_cents: cents,
        notice: notice.trim(),
        valid_days: Number(validDays) || 1,
        total_days: Number(totalDays) || 0,
        daily_inventory: Number(dailyInventory) || 0,
      })
      onDone(`已新建「${created.name}」，并铺开 ${totalDays} 天的时段`)
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-cool-ink/25" onClick={onClose}>
      <div
        className="h-full w-full max-w-[480px] overflow-y-auto border-l border-cool-line bg-cool-surface p-5 shadow-console"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="text-[15px] font-semibold text-cool-ink">新建票种</h2>
          <button onClick={onClose} className="rounded-lg border border-cool-line bg-cool-surface px-2.5 py-1 text-[12px] text-cool-ink-3">
            关闭
          </button>
        </div>

        <Field label="票种名称">
          <input value={name} onChange={(event) => setName(event.target.value)} className={INPUT} placeholder="成人票" />
        </Field>
        <Field label="类别">
          <select value={category} onChange={(event) => setCategory(event.target.value)} className={INPUT}>
            {Object.entries(TICKET_CATEGORY).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="单价（元）">
          <input value={priceYuan} onChange={(event) => setPriceYuan(event.target.value)} inputMode="decimal" className={INPUT} placeholder="100" />
        </Field>
        <Field label="有效期（天）">
          <input value={validDays} onChange={(event) => setValidDays(event.target.value)} inputMode="numeric" className={INPUT} />
        </Field>
        <Field label="票务须知">
          <textarea value={notice} onChange={(event) => setNotice(event.target.value)} rows={3} className={`${INPUT} resize-y leading-relaxed`} placeholder="凭学生证入园等说明" />
        </Field>

        <div className="mt-1 rounded-lg border border-dashed border-cool-line bg-cool-bg px-3 py-3">
          <div className="text-[12px] text-cool-ink-3">同时铺开时段</div>
          <p className="mt-1 text-[11px] leading-relaxed text-cool-ink-4">
            新票种若没有时段，游客端会显示「暂无可售日期」。默认连同未来 7 天一起建好，之后可逐时段调库存。
          </p>
          <div className="mt-2.5 grid grid-cols-2 gap-3">
            <label className="block">
              <span className="text-[11.5px] text-cool-ink-3">天数</span>
              <input value={totalDays} onChange={(event) => setTotalDays(event.target.value)} inputMode="numeric" className={INPUT} />
            </label>
            <label className="block">
              <span className="text-[11.5px] text-cool-ink-3">每日每时段库存</span>
              <input value={dailyInventory} onChange={(event) => setDailyInventory(event.target.value)} inputMode="numeric" className={INPUT} />
            </label>
          </div>
        </div>

        {error && (
          <div className="mt-3 rounded-lg border border-clay/45 bg-clay/12 px-3 py-2 text-[12.5px] text-clay-deep">{error}</div>
        )}

        <div className="mt-4 flex justify-end gap-2">
          <button onClick={onClose} className="rounded-lg border border-cool-line bg-cool-surface px-3.5 py-2 text-[12.5px] text-cool-ink-3">
            取消
          </button>
          <button
            onClick={submit}
            disabled={busy}
            className="rounded-lg bg-steel px-3.5 py-2 text-[12.5px] font-medium text-white disabled:opacity-50"
          >
            {busy ? '创建中…' : '创建'}
          </button>
        </div>
      </div>
    </div>
  )
}

const INPUT =
  'w-full rounded-lg border border-cool-line bg-cool-bg px-3 py-2 text-[12.5px] text-cool-ink outline-none placeholder:text-cool-ink-4 focus:border-steel/50'

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="mb-3 block">
      <span className="mb-1 block text-[12px] text-cool-ink-3">{label}</span>
      {children}
    </label>
  )
}
