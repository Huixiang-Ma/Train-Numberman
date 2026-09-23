/**
 * docs/09 G4 · 评价与反馈（批次 5）
 *
 * 工单编号：人工智能CV-AIGC-19-文旅Agent任务工单-创意策划与内容生成
 *
 * 安全兜底是这一页必须写清楚的一条：紧急求助走工单会经过"提交 → 客服看到 → 派单"
 * 三段延迟，而现场受伤、走失这类事一分钟都不能等。因此表单在选到「紧急求助」时
 * 置顶提示**同时联系现场工作人员**，不把线上工单包装成应急通道。
 */
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { SERVICE_CATEGORY, SERVICE_TONE, api, type ServiceRequestItem } from '../../../api/client'
import PageHeader from '../../../shared/components/PageHeader'
import StateView from '../../../shared/components/StateView'
import { useAsync } from '../../../shared/hooks/useAsync'
import { apiErrorMessage } from '../../../shared/utils/error'
import { TONE_CLASS } from '../../../shared/utils/tone'
import { visitorRef } from '../../../shared/utils/visitor'

const CATEGORIES = ['consult', 'complaint', 'lost', 'help']

export default function FeedbackPage() {
  const [category, setCategory] = useState('consult')
  const [content, setContent] = useState('')
  const [contact, setContact] = useState('')
  const [parkKeyword, setParkKeyword] = useState('')
  const [parkId, setParkId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState<ServiceRequestItem | null>(null)

  const mine = useAsync(() => api.myServiceRequests(visitorRef()), '')
  const parks = useAsync(
    () => api.parks(parkKeyword ? { keyword: parkKeyword } : {}),
    parkKeyword,
  )

  const submit = async () => {
    if (!content.trim()) {
      setError('请填写具体内容')
      return
    }
    setBusy(true)
    setError('')
    try {
      const created = await api.createServiceRequest({
        park_id: parkId || null,
        visitor_ref: visitorRef(),
        category,
        content: content.trim(),
        contact: contact.trim(),
        urgent: category === 'help',
      })
      setDone(created)
      setContent('')
      mine.reload()
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <PageHeader
        title="评价与反馈"
        desc="咨询、投诉建议、失物招领与紧急求助 · 提交后可在本页跟进处理进度"
        extra={
          <Link to="/me/orders" className="rounded-full border border-sand bg-surface px-3 py-1.5 text-[12px] text-ink-3">
            我的订单
          </Link>
        }
      />

      {category === 'help' && (
        <div className="mb-3.5 rounded-xl border border-clay/50 bg-clay/12 px-3.5 py-3 text-[12.5px] leading-relaxed text-clay-deep">
          <strong>紧急求助请同时联系现场工作人员。</strong>
          线上工单需经客服受理再派单，存在数分钟延迟；如有人身安全风险，
          请直接前往最近的游客服务中心或拨打景区应急电话。
        </div>
      )}

      {/* 提交表单 */}
      <div className="rounded-2xl border border-sand bg-surface px-4 py-4">
        <div className="flex flex-wrap gap-1.5">
          {CATEGORIES.map((key) => {
            const meta = SERVICE_CATEGORY[key]
            const active = key === category
            return (
              <button
                key={key}
                onClick={() => setCategory(key)}
                className={`rounded-full border px-3 py-1.5 text-[12.5px] ${
                  active ? 'border-amber bg-amber/10 text-amber-deep' : 'border-sand bg-surface text-ink-3'
                }`}
              >
                {meta.label}
              </button>
            )
          })}
        </div>

        <div className="mt-3.5 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="block">
            <span className="text-[12px] text-ink-3">相关景区（可留空）</span>
            <input
              value={parkKeyword}
              onChange={(event) => {
                setParkKeyword(event.target.value)
                setParkId('')
              }}
              className="mt-1 w-full rounded-lg border border-sand bg-paper px-3 py-2 text-[13px] text-ink outline-none placeholder:text-ink-4 focus:border-amber"
              placeholder="输入景区名筛选"
            />
            {parkKeyword && parks.state.kind === 'ready' && (
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {parks.state.data.items.slice(0, 6).map((park) => (
                  <button
                    key={park.id}
                    onClick={() => {
                      setParkId(park.id)
                      setParkKeyword(park.name)
                    }}
                    className={`rounded-full border px-2.5 py-1 text-[11.5px] ${
                      parkId === park.id ? 'border-amber bg-amber/10 text-amber-deep' : 'border-sand bg-surface text-ink-3'
                    }`}
                  >
                    {park.name}
                  </button>
                ))}
              </div>
            )}
          </label>
          <label className="block">
            <span className="text-[12px] text-ink-3">联系方式（便于回复）</span>
            <input
              value={contact}
              onChange={(event) => setContact(event.target.value)}
              className="mt-1 w-full rounded-lg border border-sand bg-paper px-3 py-2 text-[13px] text-ink outline-none placeholder:text-ink-4 focus:border-amber"
              placeholder="手机号或邮箱"
            />
          </label>
        </div>

        <label className="mt-3.5 block">
          <span className="text-[12px] text-ink-3">具体内容</span>
          <textarea
            value={content}
            onChange={(event) => setContent(event.target.value)}
            rows={4}
            maxLength={2000}
            className="mt-1 w-full rounded-lg border border-sand bg-paper px-3 py-2 text-[13px] leading-relaxed text-ink outline-none placeholder:text-ink-4 focus:border-amber"
            placeholder={
              category === 'lost'
                ? '请描述失物特征、遗失时间与地点…'
                : category === 'complaint'
                  ? '请描述遇到的问题与发生时间…'
                  : '请描述你的问题…'
            }
          />
          <span className="mt-1 block text-right text-[11px] text-ink-4">{content.length}/2000</span>
        </label>

        {error && (
          <div className="mt-2.5 rounded-lg border border-clay/40 bg-clay/10 px-3 py-2 text-[12.5px] text-clay-deep">{error}</div>
        )}
        {done && (
          <div className="mt-2.5 rounded-lg border border-amber/40 bg-amber/10 px-3 py-2 text-[12.5px] text-amber-deep">
            已提交，工单号 {done.id.slice(0, 8)}（{done.category_label}）。客服受理后会更新在下方列表。
          </div>
        )}

        <button
          onClick={submit}
          disabled={busy}
          className="mt-3.5 w-full rounded-xl bg-gradient-to-br from-amber to-amber-deep py-2.5 text-[13.5px] font-medium text-[#FFF8EC] disabled:opacity-50"
        >
          {busy ? '提交中…' : '提交工单'}
        </button>
      </div>

      {/* 我的工单 */}
      <section className="mt-5">
        <h2 className="mb-2.5 font-display text-[16px] text-ink">我的工单</h2>
        <StateView
          state={mine.state}
          loadingText="正在读取…"
          isEmpty={(data) => data.items.length === 0}
          emptyText="还没有提交过工单"
          onRetry={mine.reload}
        >
          {(data) => (
            <div className="flex flex-col gap-2.5">
              {data.items.map((item) => {
                const meta = SERVICE_CATEGORY[item.category] ?? { label: item.category, tone: 'idle' as const }
                return (
                  <div key={item.id} className="rounded-2xl border border-sand bg-surface px-4 py-3.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`rounded-full border px-2 py-0.5 text-[10.5px] ${TONE_CLASS[meta.tone]}`}>
                        {meta.label}
                      </span>
                      <span className={`rounded-full border px-2 py-0.5 text-[10.5px] ${TONE_CLASS[SERVICE_TONE[item.status] ?? 'idle']}`}>
                        {item.status_label}
                      </span>
                      {item.urgent && (
                        <span className="rounded-full border border-clay/45 bg-clay/12 px-2 py-0.5 text-[10.5px] text-clay-deep">
                          加急
                        </span>
                      )}
                      <span className="text-[11px] text-ink-4">
                        {item.created_at ? item.created_at.replace('T', ' ').slice(5, 16) : ''}
                      </span>
                    </div>
                    <p className="mt-1.5 text-[12.5px] leading-relaxed text-ink-2">{item.content}</p>
                    {item.reply && (
                      <div className="mt-2 rounded-xl border border-sand bg-paper px-3 py-2">
                        <div className="text-[11px] text-ink-4">
                          景区回复{item.handled_by ? ` · ${item.handled_by}` : ''}
                        </div>
                        <p className="mt-0.5 text-[12.5px] leading-relaxed text-ink-2">{item.reply}</p>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </StateView>
      </section>
    </div>
  )
}
