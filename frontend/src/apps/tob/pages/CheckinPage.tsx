/**
 * docs/09 G3 · 核销台（批次 5）
 *
 * 这一页的设计依据来自对同类景区票务后台的调研，有三条硬约束直接决定了界面形态：
 *   1. **闸口人员不是技术岗**（调研称售票/检票岗平均年龄偏高）→ 字号要大、对比要强、
 *      操作只有一个输入框和一个按钮，不做花哨的动效。
 *   2. **山区/地下基站信号弱** → 手动输入票号必须是**一等公民**，
 *      不能只依赖扫码；扫码失败时不能把用户堵在死路上。
 *   3. **防重复入园是核销的第一职责** → 失败也不能吞掉，必须用大号文字说明
 *      "上次核销的时间与闸口"，现场据此判断是重复排队还是票被复制。
 *
 * 闸口名存在 localStorage：同一台设备上的检票员不需要每次重填，
 * 而这个值会写进核销记录，是事后追溯"从哪个口进的"的唯一依据。
 */
import { useEffect, useRef, useState } from 'react'
import { api, type CheckinResult } from '../../../api/client'
import PageHeader from '../../../shared/components/PageHeader'
import { apiErrorMessage } from '../../../shared/utils/error'

const GATE_KEY = 'wenlv.checkin.gate'
const RECENT_LIMIT = 8

type Verdict =
  | { kind: 'idle' }
  | { kind: 'ok'; result: CheckinResult }
  | { kind: 'fail'; reason: string }

type RecentItem = { code: string; ok: boolean; detail: string; at: string }

export default function CheckinPage() {
  const [gate, setGate] = useState('')
  const [credential, setCredential] = useState('')
  const [busy, setBusy] = useState(false)
  const [verdict, setVerdict] = useState<Verdict>({ kind: 'idle' })
  const [recent, setRecent] = useState<RecentItem[]>([])
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    try {
      setGate(window.localStorage.getItem(GATE_KEY) ?? '')
    } catch {
      /* 存储不可用时留空，不阻断核销 */
    }
  }, [])

  const rememberGate = (value: string) => {
    setGate(value)
    try {
      window.localStorage.setItem(GATE_KEY, value)
    } catch {
      /* 同上 */
    }
  }

  const push = (item: RecentItem) => setRecent((list) => [item, ...list].slice(0, RECENT_LIMIT))

  const submit = async () => {
    const value = credential.trim()
    if (!value || busy) return
    setBusy(true)
    setVerdict({ kind: 'idle' })
    try {
      const result = await api.checkin(value, gate.trim())
      setVerdict({ kind: 'ok', result })
      push({
        code: result.code,
        ok: true,
        detail: `${result.gate} · 单内剩余 ${result.remaining_in_order} 张`,
        at: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
      })
      setCredential('')
    } catch (err) {
      const reason = apiErrorMessage(err)
      setVerdict({ kind: 'fail', reason })
      push({
        code: value,
        ok: false,
        detail: reason,
        at: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
      })
      // 失败的票号保留在框内，方便检票员核对后重试或改用手工登记
    } finally {
      setBusy(false)
      inputRef.current?.focus()
    }
  }

  return (
    <div>
      <PageHeader
        tone="cool"
        title="电子票核销台"
        desc="扫码或输入票号核销（工单 docs/09 G3）· 需运营及以上角色，一票一核销、不可重复入园"
      />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        {/* 核销区：大字号、高对比 */}
        <div className="rounded-xl border border-cool-line bg-cool-surface p-5 shadow-console">
          <label className="block">
            <span className="text-[13px] font-medium text-cool-ink">闸口</span>
            <input
              value={gate}
              onChange={(event) => rememberGate(event.target.value)}
              placeholder="如：南门一号闸"
              className="mt-1.5 w-full rounded-lg border border-cool-line bg-cool-bg px-3.5 py-3 text-[15px] text-cool-ink outline-none placeholder:text-cool-ink-4 focus:border-steel/60"
            />
            <span className="mt-1 block text-[11.5px] text-cool-ink-4">
              会写入核销记录，用于事后追溯从哪个闸口入园；本机记住该值
            </span>
          </label>

          <label className="mt-4 block">
            <span className="text-[13px] font-medium text-cool-ink">票号 / 二维码内容</span>
            <input
              ref={inputRef}
              value={credential}
              onChange={(event) => setCredential(event.target.value)}
              onKeyDown={(event) => {
                // 扫码枪一般以回车结尾；手动输入也习惯按回车提交
                if (event.key === 'Enter') void submit()
              }}
              autoFocus
              placeholder="扫描二维码或手工输入票号（T 开头）"
              className="mt-1.5 w-full rounded-lg border-2 border-cool-line bg-cool-bg px-3.5 py-4 font-mono text-[19px] tracking-wider text-cool-ink outline-none placeholder:font-ui placeholder:text-[14px] placeholder:tracking-normal placeholder:text-cool-ink-4 focus:border-steel"
            />
          </label>

          <button
            onClick={submit}
            disabled={busy || !credential.trim()}
            className="mt-4 w-full rounded-xl bg-steel py-4 text-[17px] font-semibold text-white disabled:cursor-not-allowed disabled:opacity-45"
          >
            {busy ? '核销中…' : '核 销'}
          </button>

          {/* 结果横幅：成功/失败都要大到一眼能看清 */}
          {verdict.kind === 'ok' && (
            <div className="mt-4 rounded-xl border-2 border-steel/50 bg-steel/10 px-4 py-4">
              <div className="flex items-center gap-2.5">
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-steel text-[20px] font-bold text-white">
                  ✓
                </span>
                <div>
                  <div className="text-[19px] font-semibold text-steel-deep">核销成功，请放行</div>
                  <div className="mt-0.5 font-mono text-[13px] text-cool-ink-2">{verdict.result.code}</div>
                </div>
              </div>
              <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 border-t border-steel/25 pt-3 text-[13px]">
                <div>
                  <dt className="text-cool-ink-3">订单号</dt>
                  <dd className="font-mono text-cool-ink">{verdict.result.order_no}</dd>
                </div>
                <div>
                  <dt className="text-cool-ink-3">订单状态</dt>
                  <dd className="text-cool-ink">{verdict.result.order_status_label}</dd>
                </div>
                <div>
                  <dt className="text-cool-ink-3">核销闸口</dt>
                  <dd className="text-cool-ink">{verdict.result.gate}</dd>
                </div>
                <div>
                  <dt className="text-cool-ink-3">单内剩余待核销</dt>
                  <dd className="text-cool-ink">
                    {verdict.result.remaining_in_order} 张
                    {verdict.result.remaining_in_order > 0 && (
                      <span className="ml-1.5 text-[11.5px] text-cool-ink-3">（同行人员仍需逐张出示）</span>
                    )}
                  </dd>
                </div>
              </dl>
            </div>
          )}

          {verdict.kind === 'fail' && (
            <div className="mt-4 rounded-xl border-2 border-clay/60 bg-clay/12 px-4 py-4">
              <div className="flex items-start gap-2.5">
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-clay text-[20px] font-bold text-white">
                  !
                </span>
                <div>
                  <div className="text-[19px] font-semibold text-clay-deep">核销未通过，请勿放行</div>
                  <p className="mt-1 text-[13.5px] leading-relaxed text-clay-deep">{verdict.reason}</p>
                  <p className="mt-2 text-[11.5px] leading-relaxed text-clay">
                    如游客坚持已购票，请让其打开「我的订单」出示电子票，或到游客服务中心人工核对订单号。
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* 本机核销记录 */}
        <div className="rounded-xl border border-cool-line bg-cool-surface p-4 shadow-console">
          <div className="flex items-baseline justify-between gap-2">
            <h2 className="text-[13px] font-medium text-cool-ink">本机核销记录</h2>
            <span className="text-[11px] text-cool-ink-4">仅本机最近 {RECENT_LIMIT} 条</span>
          </div>
          {recent.length === 0 ? (
            <div className="mt-3 rounded-lg border border-dashed border-cool-line bg-cool-bg px-3.5 py-8 text-center text-[12.5px] text-cool-ink-3">
              还没有核销记录
            </div>
          ) : (
            <ul className="mt-3 flex flex-col gap-1.5">
              {recent.map((item, index) => (
                <li
                  key={`${item.code}-${index}`}
                  className={`rounded-lg border px-3 py-2 ${
                    item.ok ? 'border-steel/35 bg-steel/10' : 'border-clay/45 bg-clay/12'
                  }`}
                >
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="font-mono text-[12px] text-cool-ink">{item.code}</span>
                    <span className="shrink-0 text-[11px] text-cool-ink-3">{item.at}</span>
                  </div>
                  <div className={`mt-0.5 text-[11.5px] ${item.ok ? 'text-steel-deep' : 'text-clay-deep'}`}>
                    {item.ok ? '已核销' : '未通过'} · {item.detail}
                  </div>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-3 border-t border-cool-line pt-3 text-[11px] leading-relaxed text-cool-ink-4">
            完整核销记录以后端订单与电子票状态为准，本列表仅作现场即时核对，
            刷新页面即清空，不作为对账依据。
          </p>
        </div>
      </div>
    </div>
  )
}
