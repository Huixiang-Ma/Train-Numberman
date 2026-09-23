/**
 * 工单17 §5 · 审核与合规（批次 4）
 *
 * 数据来自两个既有接口，均为**运营及以上**角色：
 *   - `/audit/compliance` 合规自查：后端刻意不粉饰，未配置项如实为 pending
 *   - `/audit/logs`       操作审计：仅状态变更类请求落库，已脱敏
 *
 * 设计取舍：合规项按"待处理优先"排序而不是按后端返回顺序。
 * 运营打开这一页是为了看**还差什么**，绿项是背景信息。
 */
import { useState } from 'react'
import { api, httpTone, type ComplianceCheck } from '../../../api/client'
import PageHeader from '../../../shared/components/PageHeader'
import StateView from '../../../shared/components/StateView'
import { useAsync } from '../../../shared/hooks/useAsync'
import { TONE_CLASS } from '../../../shared/utils/tone'

export default function ReviewPage() {
  const [limit, setLimit] = useState(50)
  const [pathFilter, setPathFilter] = useState('')
  const [draft, setDraft] = useState('')

  const compliance = useAsync(() => api.compliance(), '')
  const logs = useAsync(() => api.auditLogs({ limit, path: pathFilter || undefined }), `${limit}|${pathFilter}`)

  return (
    <div>
      <PageHeader
        tone="cool"
        title="审核与合规"
        desc="合规自查清单与操作审计（工单17 §5）· 需运营及以上角色，未登录将被前端拦在登录页"
        extra={
          <button
            onClick={() => {
              compliance.reload()
              logs.reload()
            }}
            className="rounded-lg border border-cool-line bg-cool-surface px-3 py-1.5 text-[12.5px] text-cool-ink-2 hover:border-steel/40 hover:text-steel-deep"
          >
            刷新
          </button>
        }
      />

      {/* 合规自查 */}
      <section className="mb-6">
        <h2 className="mb-2.5 text-[13px] font-medium text-cool-ink">合规自查</h2>
        <StateView
          state={compliance.state}
          tone="cool"
          loadingText="正在自查…"
          onRetry={compliance.reload}
        >
          {(data) => {
            const sorted = [...data.checks].sort((a, b) => {
              const rank = (item: ComplianceCheck) => (item.status === 'ok' ? 1 : 0)
              return rank(a) - rank(b)
            })
            return (
              <div className="flex flex-col gap-3">
                <div
                  className={`rounded-lg border px-3.5 py-2 text-[12.5px] ${
                    data.pending > 0
                      ? 'border-amber/40 bg-amber/10 text-amber-deep'
                      : 'border-steel/35 bg-steel/10 text-steel-deep'
                  }`}
                >
                  {data.pending > 0
                    ? `${data.pending} 项待落实。清单如实回显当前配置，未启用的项不会显示为已通过。`
                    : '全部自查项已落实。'}
                </div>
                <div className="grid grid-cols-1 gap-2.5 md:grid-cols-2 xl:grid-cols-3">
                  {sorted.map((item) => (
                    <div key={item.item} className="rounded-xl border border-cool-line bg-cool-surface p-3.5 shadow-console">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-[12.5px] font-medium text-cool-ink">{item.item}</span>
                        <span
                          className={`shrink-0 rounded-full border px-2 py-0.5 text-[10.5px] ${
                            item.status === 'ok' ? TONE_CLASS.ok : TONE_CLASS.warn
                          }`}
                        >
                          {item.status === 'ok' ? '已落实' : '待落实'}
                        </span>
                      </div>
                      <p className="mt-1.5 text-[11.5px] leading-relaxed text-cool-ink-3">{item.detail}</p>
                    </div>
                  ))}
                </div>
              </div>
            )
          }}
        </StateView>
      </section>

      {/* 审计日志 */}
      <section>
        <div className="mb-2.5 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-[13px] font-medium text-cool-ink">操作审计</h2>
          <div className="flex flex-wrap items-center gap-2">
            <form
              className="flex gap-2"
              onSubmit={(event) => {
                event.preventDefault()
                setPathFilter(draft.trim())
              }}
            >
              <input
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                placeholder="按请求路径筛选…"
                className="w-[190px] rounded-lg border border-cool-line bg-cool-bg px-3 py-1.5 text-[12px] text-cool-ink outline-none placeholder:text-cool-ink-4 focus:border-steel/50"
              />
              <button type="submit" className="rounded-lg bg-steel px-3 py-1.5 text-[12px] text-white">
                筛选
              </button>
            </form>
            <label className="flex items-center gap-1.5 text-[12px] text-cool-ink-3">
              条数
              <select
                value={limit}
                onChange={(event) => setLimit(Number(event.target.value))}
                className="rounded-lg border border-cool-line bg-cool-bg px-2 py-1.5 text-[12px] text-cool-ink outline-none focus:border-steel/50"
              >
                {[20, 50, 100, 200].map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
            {pathFilter && (
              <button
                onClick={() => {
                  setDraft('')
                  setPathFilter('')
                }}
                className="rounded-lg border border-cool-line bg-cool-surface px-2.5 py-1.5 text-[12px] text-cool-ink-3"
              >
                重置
              </button>
            )}
          </div>
        </div>

        <StateView
          state={logs.state}
          tone="cool"
          loadingText="正在读取审计日志…"
          isEmpty={(data) => data.items.length === 0}
          emptyText="还没有审计记录。审计只记录状态变更类请求，浏览类请求不入库。"
          onRetry={logs.reload}
        >
          {(data) => (
            <div className="flex flex-col gap-3">
              <div className="text-[11.5px] text-cool-ink-3">
                共 {data.total} 条，显示其中 {data.items.length} 条 · 路径与来源 IP 已在后端写入前脱敏
              </div>
              <div className="overflow-hidden rounded-xl border border-cool-line bg-cool-surface shadow-console">
                <div className="overflow-x-auto">
                  <table className="w-full border-collapse text-[12.5px]">
                    <thead>
                      <tr className="bg-cool-surface-2 text-left text-cool-ink-3">
                        <th className="px-3.5 py-2.5 font-medium">时间</th>
                        <th className="px-3.5 py-2.5 font-medium">方法</th>
                        <th className="px-3.5 py-2.5 font-medium">路径</th>
                        <th className="px-3.5 py-2.5 font-medium">状态</th>
                        <th className="px-3.5 py-2.5 font-medium">角色</th>
                        <th className="px-3.5 py-2.5 font-medium">来源</th>
                        <th className="px-3.5 py-2.5 font-medium">trace</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.items.map((item) => (
                        <tr key={item.id} className="border-t border-cool-line hover:bg-cool-surface-2/60">
                          <td className="whitespace-nowrap px-3.5 py-2.5 text-cool-ink-3">
                            {item.created_at ? item.created_at.replace('T', ' ').slice(0, 19) : '—'}
                          </td>
                          <td className="px-3.5 py-2.5 font-medium text-cool-ink-2">{item.method}</td>
                          <td className="max-w-[260px] truncate px-3.5 py-2.5 text-cool-ink-2" title={item.path}>
                            {item.path}
                          </td>
                          <td className="px-3.5 py-2.5">
                            <span className={`rounded-full border px-2 py-0.5 text-[10.5px] ${TONE_CLASS[httpTone(item.status)]}`}>
                              {item.status ?? '—'}
                            </span>
                          </td>
                          <td className="px-3.5 py-2.5 text-cool-ink-3">{item.role ?? '—'}</td>
                          <td className="px-3.5 py-2.5 text-cool-ink-3">{item.client_ip ?? '—'}</td>
                          <td className="px-3.5 py-2.5 font-mono text-[11px] text-cool-ink-4">
                            {item.trace_id ? item.trace_id.slice(0, 8) : '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </StateView>
      </section>
    </div>
  )
}
