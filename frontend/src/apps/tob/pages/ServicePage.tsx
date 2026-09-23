/**
 * docs/09 G4 · 游客服务工单（批次 5）
 *
 * 排序不在这里做，也不许在这里改：后端已经按「待受理 → 加急 → 类型优先级 → 时间倒序」
 * 排好。前端若再排一次，两侧规则一旦不同就会出现"列表顺序与统计口径打架"，
 * 而现场按列表从上往下处理，顺序错了意味着先处理咨询、后处理紧急求助。
 *
 * 紧急求助用红色整条标出而不是只加个标签：客服在一屏十几条工单里，
 * 靠一个 10px 的小标签找不出真正紧急的那条。
 */
import { useState } from 'react'
import { SERVICE_CATEGORY, SERVICE_TONE, api, type ServiceRequestItem } from '../../../api/client'
import PageHeader from '../../../shared/components/PageHeader'
import StateView from '../../../shared/components/StateView'
import { useAsync } from '../../../shared/hooks/useAsync'
import { apiErrorMessage } from '../../../shared/utils/error'
import { TONE_CLASS } from '../../../shared/utils/tone'

const CATEGORY_TABS = [
  { value: '', label: '全部' },
  { value: 'help', label: '紧急求助' },
  { value: 'complaint', label: '投诉建议' },
  { value: 'lost', label: '失物招领' },
  { value: 'consult', label: '咨询' },
]

const STATUS_TABS = [
  { value: '', label: '全部' },
  { value: 'open', label: '待受理' },
  { value: 'processing', label: '处理中' },
  { value: 'resolved', label: '已回复' },
  { value: 'closed', label: '已关闭' },
]

export default function ServicePage() {
  const [category, setCategory] = useState('')
  const [status, setStatus] = useState('')
  const [parkId, setParkId] = useState('')
  const [replyTo, setReplyTo] = useState<ServiceRequestItem | null>(null)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')

  const parks = useAsync(() => api.parks({ limit: 200 }), '')
  const requests = useAsync(
    () =>
      api.adminServiceRequests({
        category: category || undefined,
        status: status || undefined,
        park_id: parkId || undefined,
      }),
    `${category}|${status}|${parkId}`,
  )
  const stats = useAsync(() => api.serviceStats(parkId || undefined), parkId)

  const flash = (message: string, isError = false) => {
    setNotice(isError ? '' : message)
    setError(isError ? message : '')
  }

  const reload = () => {
    requests.reload()
    stats.reload()
  }

  const setStatusOf = async (item: ServiceRequestItem, next: string) => {
    try {
      await api.setServiceStatus(item.id, next)
      flash(`工单已置为「${STATUS_TABS.find((tab) => tab.value === next)?.label ?? next}」`)
      reload()
    } catch (err) {
      flash(apiErrorMessage(err), true)
    }
  }

  return (
    <div>
      <PageHeader
        tone="cool"
        title="游客服务工单"
        desc="咨询 / 投诉建议 / 失物招领 / 紧急求助的受理与回复（docs/09 G4）· 顺序由后端按紧急度排定"
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

      {/* 服务汇总 */}
      <StateView state={stats.state} tone="cool" loadingText="正在汇总…" onRetry={stats.reload}>
        {(data) => (
          <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-5">
            {[
              { label: '工单总数', value: data.total },
              { label: '待受理', value: data.open, tone: 'warn' as const },
              { label: '加急待处理', value: data.urgent_open, tone: 'down' as const },
              { label: '已解决', value: data.resolved },
              { label: '平均响应', value: data.avg_response_minutes == null ? '—' : `${data.avg_response_minutes} 分钟` },
            ].map((item) => (
              <div key={item.label} className="rounded-xl border border-cool-line bg-cool-surface px-3.5 py-3 shadow-console">
                <div className="text-[11.5px] text-cool-ink-3">{item.label}</div>
                <div
                  className={`mt-0.5 text-[19px] font-semibold ${
                    item.tone === 'down' ? 'text-clay-deep' : item.tone === 'warn' ? 'text-amber-deep' : 'text-cool-ink'
                  }`}
                >
                  {item.value}
                </div>
              </div>
            ))}
          </div>
        )}
      </StateView>

      {/* 筛选 */}
      <div className="mb-4 flex flex-wrap items-center gap-2 rounded-xl border border-cool-line bg-cool-surface px-3.5 py-3 shadow-console">
        <div className="scroll-x">
          {CATEGORY_TABS.map((tab) => (
            <button
              key={tab.value}
              onClick={() => setCategory(tab.value)}
              className={`rounded-full border px-3 py-1.5 text-[12px] ${
                category === tab.value
                  ? 'border-steel/45 bg-steel/10 font-medium text-steel-deep'
                  : 'border-cool-line bg-cool-surface-2 text-cool-ink-3'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <div className="scroll-x">
          {STATUS_TABS.map((tab) => (
            <button
              key={tab.value}
              onClick={() => setStatus(tab.value)}
              className={`rounded-full border px-3 py-1.5 text-[12px] ${
                status === tab.value
                  ? 'border-steel/45 bg-steel/10 font-medium text-steel-deep'
                  : 'border-cool-line bg-cool-surface-2 text-cool-ink-3'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-1.5 text-[12px] text-cool-ink-3">
          景区
          <select
            value={parkId}
            onChange={(event) => setParkId(event.target.value)}
            className="min-w-[140px] rounded-lg border border-cool-line bg-cool-bg px-2 py-2 text-[12.5px] text-cool-ink outline-none focus:border-steel/50"
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
      </div>

      <StateView
        state={requests.state}
        tone="cool"
        loadingText="正在读取工单…"
        isEmpty={(data) => data.items.length === 0}
        emptyText="没有匹配的工单。游客提交后会自动出现在这里。"
        onRetry={requests.reload}
      >
        {(data) => (
          <div className="flex flex-col gap-2.5">
            {data.items.map((item) => {
              const meta = SERVICE_CATEGORY[item.category] ?? { label: item.category, tone: 'idle' as const }
              const urgentOpen = item.urgent && item.status === 'open'
              return (
                <div
                  key={item.id}
                  className={`rounded-xl border bg-cool-surface px-4 py-3.5 shadow-console ${
                    urgentOpen ? 'border-clay/60' : 'border-cool-line'
                  }`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      {urgentOpen && (
                        <span className="rounded-full border border-clay/60 bg-clay/15 px-2.5 py-0.5 text-[11px] font-semibold text-clay-deep">
                          加急 · 待受理
                        </span>
                      )}
                      <span className={`rounded-full border px-2 py-0.5 text-[10.5px] ${TONE_CLASS[meta.tone]}`}>
                        {meta.label}
                      </span>
                      <span className={`rounded-full border px-2 py-0.5 text-[10.5px] ${TONE_CLASS[SERVICE_TONE[item.status] ?? 'idle']}`}>
                        {item.status_label}
                      </span>
                      {!urgentOpen && item.urgent && (
                        <span className="rounded-full border border-clay/45 bg-clay/12 px-2 py-0.5 text-[10.5px] text-clay-deep">
                          加急
                        </span>
                      )}
                      <span className="text-[11px] text-cool-ink-4">
                        {item.created_at ? item.created_at.replace('T', ' ').slice(0, 16) : ''}
                      </span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <button
                        onClick={() => setReplyTo(item)}
                        className="rounded-lg bg-steel px-2.5 py-1 text-[11.5px] text-white"
                      >
                        {item.reply ? '修改回复' : '回复'}
                      </button>
                      {item.status !== 'processing' && item.status !== 'resolved' && (
                        <button
                          onClick={() => setStatusOf(item, 'processing')}
                          className="rounded-lg border border-cool-line bg-cool-surface px-2.5 py-1 text-[11.5px] text-cool-ink-2 hover:border-steel/40"
                        >
                          受理
                        </button>
                      )}
                      {item.status !== 'closed' && (
                        <button
                          onClick={() => setStatusOf(item, 'closed')}
                          className="rounded-lg border border-cool-line bg-cool-surface px-2.5 py-1 text-[11.5px] text-cool-ink-3 hover:border-steel/40"
                        >
                          关闭
                        </button>
                      )}
                    </div>
                  </div>

                  <p className="mt-2 text-[12.5px] leading-relaxed text-cool-ink-2">{item.content}</p>

                  <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-cool-ink-4">
                    {item.contact && <span>联系方式 {item.contact}</span>}
                    {item.park_id && <span>景区 {item.park_id.slice(0, 8)}…</span>}
                    <span>工单号 {item.id.slice(0, 8)}</span>
                  </div>

                  {item.reply && (
                    <div className="mt-2.5 rounded-lg border border-steel/35 bg-steel/10 px-3 py-2">
                      <div className="text-[11px] text-steel-deep">
                        已回复{item.handled_by ? ` · ${item.handled_by}` : ''}
                        {item.replied_at ? ` · ${item.replied_at.replace('T', ' ').slice(0, 16)}` : ''}
                      </div>
                      <p className="mt-0.5 text-[12.5px] leading-relaxed text-cool-ink-2">{item.reply}</p>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </StateView>

      {replyTo && (
        <ReplyDrawer
          item={replyTo}
          onClose={() => setReplyTo(null)}
          onDone={(message) => {
            setReplyTo(null)
            flash(message)
            reload()
          }}
          onError={(message) => flash(message, true)}
        />
      )}
    </div>
  )
}

function ReplyDrawer({
  item,
  onClose,
  onDone,
  onError,
}: {
  item: ServiceRequestItem
  onClose: () => void
  onDone: (message: string) => void
  onError: (message: string) => void
}) {
  const [reply, setReply] = useState(item.reply)
  const [handler, setHandler] = useState(item.handled_by)
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    if (!reply.trim()) {
      onError('回复内容不能为空')
      return
    }
    setBusy(true)
    try {
      await api.replyServiceRequest(item.id, reply.trim(), handler.trim())
      onDone('回复已提交，工单状态转为已回复')
    } catch (err) {
      onError(apiErrorMessage(err))
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
          <h2 className="text-[15px] font-semibold text-cool-ink">回复工单</h2>
          <button onClick={onClose} className="rounded-lg border border-cool-line bg-cool-surface px-2.5 py-1 text-[12px] text-cool-ink-3">
            关闭
          </button>
        </div>

        <div className="mb-4 rounded-lg border border-cool-line bg-cool-bg px-3.5 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`rounded-full border px-2 py-0.5 text-[10.5px] ${TONE_CLASS[SERVICE_CATEGORY[item.category]?.tone ?? 'idle']}`}>
              {item.category_label}
            </span>
            {item.urgent && (
              <span className="rounded-full border border-clay/45 bg-clay/12 px-2 py-0.5 text-[10.5px] text-clay-deep">加急</span>
            )}
            <span className="text-[11px] text-cool-ink-4">
              {item.created_at ? item.created_at.replace('T', ' ').slice(0, 16) : ''}
            </span>
          </div>
          <p className="mt-1.5 text-[12.5px] leading-relaxed text-cool-ink-2">{item.content}</p>
          {item.contact && <div className="mt-1 text-[11px] text-cool-ink-3">联系方式 {item.contact}</div>}
        </div>

        <label className="mb-3 block">
          <span className="mb-1 block text-[12px] text-cool-ink-3">回复内容（提交后游客端可见）</span>
          <textarea
            value={reply}
            onChange={(event) => setReply(event.target.value)}
            rows={6}
            className="w-full resize-y rounded-lg border border-cool-line bg-cool-bg px-3 py-2 text-[12.5px] leading-relaxed text-cool-ink outline-none placeholder:text-cool-ink-4 focus:border-steel/50"
            placeholder="如：已联系服务台，轮椅 5 分钟内送达南门。"
          />
        </label>

        <label className="mb-3 block">
          <span className="mb-1 block text-[12px] text-cool-ink-3">处理人</span>
          <input
            value={handler}
            onChange={(event) => setHandler(event.target.value)}
            className="w-full rounded-lg border border-cool-line bg-cool-bg px-3 py-2 text-[12.5px] text-cool-ink outline-none focus:border-steel/50"
            placeholder="填写处理人，便于事后追溯"
          />
        </label>

        <p className="mb-4 text-[11px] leading-relaxed text-cool-ink-4">
          提交回复会把工单状态置为「已回复」。若问题仍需跟进，可再手动改为「处理中」。
        </p>

        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="rounded-lg border border-cool-line bg-cool-surface px-3.5 py-2 text-[12.5px] text-cool-ink-3">
            取消
          </button>
          <button
            onClick={submit}
            disabled={busy}
            className="rounded-lg bg-steel px-3.5 py-2 text-[12.5px] font-medium text-white disabled:opacity-50"
          >
            {busy ? '提交中…' : '提交回复'}
          </button>
        </div>
      </div>
    </div>
  )
}
