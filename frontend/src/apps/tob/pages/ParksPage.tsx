/**
 * docs/09 G1/G2 · ToB 景区管理（列表）
 * 工单16 §2.1「景区管理者」的核心工作面。
 *
 * 设计取向（依据网络样本调研的行业约束）：
 *   - 后台使用者可能包括售票/检票等非技术岗，界面按"高密度但一眼可读"来做：
 *     表格固定表头、状态用语义色标签、关键字筛选放在最显眼处
 *   - 冷色体系，与游客端的暖色沉浸形成明确区分（docs/08 §6）
 *   - 只读视图；增删改属批次 4 的写接口
 */
import { useState } from 'react'
import { PARK_STATUS, api } from '../../../api/client'
import PageHeader from '../../../shared/components/PageHeader'
import StateView from '../../../shared/components/StateView'
import { useAsync } from '../../../shared/hooks/useAsync'
import { TONE_CLASS } from '../../../shared/utils/tone'

export default function ParksPage() {
  const [draft, setDraft] = useState('')
  const [keyword, setKeyword] = useState('')
  const [destinationId, setDestinationId] = useState('')
  const [status, setStatus] = useState('')

  const destinations = useAsync(() => api.destinations(), 'destinations')
  const parks = useAsync(
    () =>
      api.parks({
        keyword: keyword || undefined,
        destination_id: destinationId || undefined,
      }),
    `${keyword}|${destinationId}`,
  )

  return (
    <div>
      <PageHeader
        tone="cool"
        title="景区与景点管理"
        desc="多目的地 / 多景区统一台账（docs/09 G1）· 写接口将在批次 4 提供"
        extra={
          <button
            onClick={parks.reload}
            className="rounded-lg border border-cool-line bg-cool-surface px-3 py-1.5 text-[12.5px] text-cool-ink-2 hover:border-steel/40 hover:text-steel-deep"
          >
            刷新
          </button>
        }
      />

      {/* 筛选条 */}
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
            placeholder="搜索景区名称或简介…"
            className="min-w-0 flex-1 rounded-lg border border-cool-line bg-cool-bg px-3 py-2 text-[12.5px] text-cool-ink outline-none placeholder:text-cool-ink-4 focus:border-steel/50"
          />
          <button type="submit" className="rounded-lg bg-steel px-3.5 py-2 text-[12.5px] text-white">
            搜索
          </button>
        </form>

        <label className="flex items-center gap-1.5 text-[12px] text-cool-ink-3">
          目的地
          <select
            value={destinationId}
            onChange={(event) => setDestinationId(event.target.value)}
            className="rounded-lg border border-cool-line bg-cool-bg px-2 py-2 text-[12.5px] text-cool-ink outline-none focus:border-steel/50"
          >
            <option value="">全部</option>
            {destinations.state.kind === 'ready' &&
              destinations.state.data.items.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
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
            <option value="">全部</option>
            {Object.entries(PARK_STATUS).map(([value, item]) => (
              <option key={value} value={value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>

        {(keyword || destinationId || status) && (
          <button
            onClick={() => {
              setDraft('')
              setKeyword('')
              setDestinationId('')
              setStatus('')
            }}
            className="rounded-lg border border-cool-line bg-cool-surface px-3 py-2 text-[12.5px] text-cool-ink-3"
          >
            重置
          </button>
        )}
      </div>

      <StateView
        state={parks.state}
        tone="cool"
        loadingText="正在读取景区台账…"
        isEmpty={(data) => data.items.length === 0}
        emptyText="没有匹配的景区，试试调整筛选条件"
        onRetry={parks.reload}
      >
        {(data) => {
          // 状态筛选在前端做：当前景区量级（十位）不值得为它多一个后端参数，
          // 且能让筛选立即生效、不触发请求。数据量上去后应下推到服务端。
          const rows = status ? data.items.filter((item) => item.status === status) : data.items
          const openCount = rows.filter((item) => item.status === 'open').length
          const attractionTotal = rows.reduce((sum, item) => sum + item.attraction_count, 0)

          return (
            <div className="flex flex-col gap-4">
              {/* 指标条 */}
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {[
                  { label: '景区总数', value: rows.length },
                  { label: '营业中', value: openCount },
                  { label: '景点总数', value: attractionTotal },
                  { label: '日承载合计', value: rows.reduce((sum, item) => sum + item.daily_capacity, 0).toLocaleString() },
                ].map((item) => (
                  <div key={item.label} className="rounded-xl border border-cool-line bg-cool-surface px-3.5 py-3 shadow-console">
                    <div className="text-[11.5px] text-cool-ink-3">{item.label}</div>
                    <div className="mt-0.5 text-[19px] font-semibold text-cool-ink">{item.value}</div>
                  </div>
                ))}
              </div>

              {rows.length === 0 ? (
                <div className="rounded-xl border border-dashed border-cool-line bg-cool-surface px-4 py-8 text-center text-[13px] text-cool-ink-3">
                  该状态下没有景区
                </div>
              ) : (
                <div className="overflow-hidden rounded-xl border border-cool-line bg-cool-surface shadow-console">
                  <div className="overflow-x-auto">
                    <table className="w-full border-collapse text-[12.5px]">
                      <thead>
                        <tr className="bg-cool-surface-2 text-left text-cool-ink-3">
                          <th className="px-3.5 py-2.5 font-medium">景区</th>
                          <th className="px-3.5 py-2.5 font-medium">目的地</th>
                          <th className="px-3.5 py-2.5 font-medium">等级</th>
                          <th className="px-3.5 py-2.5 font-medium">状态</th>
                          <th className="px-3.5 py-2.5 text-right font-medium">景点</th>
                          <th className="px-3.5 py-2.5 text-right font-medium">日承载</th>
                          <th className="px-3.5 py-2.5 font-medium">开放时间</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((item) => {
                          const tone = PARK_STATUS[item.status]
                          return (
                            <tr key={item.id} className="border-t border-cool-line hover:bg-cool-surface-2/60">
                              <td className="px-3.5 py-2.5">
                                <div className="font-medium text-cool-ink">{item.name}</div>
                                <div className="mt-0.5 max-w-[320px] truncate text-[11.5px] text-cool-ink-3" title={item.summary}>
                                  {item.summary}
                                </div>
                              </td>
                              <td className="px-3.5 py-2.5 text-cool-ink-2">{item.destination_name ?? '未归属'}</td>
                              <td className="px-3.5 py-2.5 text-cool-ink-2">{item.level || '—'}</td>
                              <td className="px-3.5 py-2.5">
                                <span className={`rounded-full border px-2 py-0.5 text-[10.5px] ${TONE_CLASS[tone?.tone ?? 'idle']}`}>
                                  {tone?.label ?? item.status}
                                </span>
                              </td>
                              <td className="px-3.5 py-2.5 text-right text-cool-ink-2">{item.attraction_count}</td>
                              <td className="px-3.5 py-2.5 text-right text-cool-ink-2">
                                {item.daily_capacity > 0 ? item.daily_capacity.toLocaleString() : '—'}
                              </td>
                              <td className="px-3.5 py-2.5 text-cool-ink-3">{item.open_hours || '—'}</td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              <p className="text-[11.5px] text-cool-ink-4">
                本页为只读台账。景区与景点的增删改、多媒体素材挂载属批次 4（docs/09 G2）。
              </p>
            </div>
          )
        }}
      </StateView>
    </div>
  )
}
