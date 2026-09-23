/**
 * docs/09 G1 · ToC 发现页（多目的地 / 多景区浏览）
 * 工单17 §2 结构化数据 + §2.5 本地化内容扩展；工单16 §2.2 场景 S1 的入口。
 *
 * 设计取向：暖色沉浸、低密度卡片流、移动优先。
 * 与批次 0 的首页区别：首页是"平台说明 + 模块入口"，这里是真正的浏览页。
 */
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { PARK_STATUS, api, formatDistance } from '../../../api/client'
import EmptyState from '../../../shared/components/EmptyState'
import StateView from '../../../shared/components/StateView'
import { useAsync } from '../../../shared/hooks/useAsync'
import { TONE_CLASS } from '../../../shared/utils/tone'

export default function ExplorePage() {
  // draft 是输入框的字，keyword 是"提交后生效"的词 —— 分开可以让输入不触发请求
  const [draft, setDraft] = useState('')
  const [keyword, setKeyword] = useState('')
  const [tag, setTag] = useState<string | null>(null)
  const [destinationId, setDestinationId] = useState<string | null>(null)

  const destinations = useAsync(() => api.destinations(), 'destinations')
  const parks = useAsync(
    () =>
      api.parks({
        keyword: keyword || undefined,
        tag: tag ?? undefined,
        destination_id: destinationId ?? undefined,
      }),
    `${keyword}|${tag ?? ''}|${destinationId ?? ''}`,
  )

  // 标签来源用目的地的标签而不是当前景区结果：否则一按筛选，候选标签就自我塌缩成一项
  const themeTags = Array.from(new Set((destinations.state.kind === 'ready' ? destinations.state.data.items : []).flatMap((item) => item.tags)))

  const picked = destinationId ? destinations.state.kind === 'ready' && destinations.state.data.items.find((item) => item.id === destinationId) : null

  return (
    <div className="flex flex-col gap-5">
      {/* 搜索 */}
      <section className="rounded-2xl border border-sand bg-surface/70 px-4 py-4 shadow-panel sm:px-5">
        <div className="font-display text-[19px] leading-tight text-ink">想去哪儿看看？</div>
        <p className="mt-1 text-[12.5px] text-ink-3">输入景区或主题关键词，例如「园林」「海丝」「亲子」</p>
        <form
          className="mt-3 flex gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            setKeyword(draft.trim())
          }}
        >
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="搜索景区…"
            className="min-w-0 flex-1 rounded-xl border border-sand bg-surface px-3.5 py-2.5 text-[13.5px] text-ink outline-none placeholder:text-ink-4 focus:border-amber/50"
          />
          <button type="submit" className="rounded-xl bg-gradient-to-br from-amber-soft to-amber-deep px-4 py-2.5 text-[13.5px] text-[#FFF8EC]">
            搜索
          </button>
          {(keyword || tag || destinationId) && (
            <button
              type="button"
              onClick={() => {
                setDraft('')
                setKeyword('')
                setTag(null)
                setDestinationId(null)
              }}
              className="rounded-xl border border-sand bg-surface px-3 py-2.5 text-[12.5px] text-ink-3"
            >
              重置
            </button>
          )}
        </form>

        {themeTags.length > 0 && (
          <div className="scroll-x mt-3">
            {themeTags.map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => setTag(tag === item ? null : item)}
                className={`rounded-full border px-3 py-1 text-[12px] transition ${
                  tag === item ? 'border-amber bg-amber/12 text-amber-deep' : 'border-sand bg-surface text-ink-3'
                }`}
              >
                {item}
              </button>
            ))}
          </div>
        )}
      </section>

      {/* 目的地 */}
      <section>
        <div className="mb-3 font-display text-[16px] text-ink">目的地</div>
        <StateView state={destinations.state} tone="warm" loadingText="正在读取目的地…" emptyText="暂无目的地数据">
          {(data) => (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {data.items.map((item) => {
                const active = destinationId === item.id
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setDestinationId(active ? null : item.id)}
                    className={`rounded-2xl border px-4 py-3.5 text-left transition ${
                      active ? 'border-amber bg-amber/12 shadow-panel' : 'border-sand bg-surface hover:border-amber/45'
                    }`}
                  >
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="font-display text-[17px] text-ink">{item.name}</span>
                      <span className="shrink-0 text-[11.5px] text-ink-3">{item.park_count} 个景区</span>
                    </div>
                    <div className="mt-0.5 text-[11.5px] text-ink-4">{item.region}</div>
                    <div className="mt-1.5 text-[12.5px] leading-relaxed text-ink-2">{item.summary}</div>
                  </button>
                )
              })}
            </div>
          )}
        </StateView>
      </section>

      {/* 景区 */}
      <section>
        <div className="mb-3 flex items-baseline justify-between gap-3">
          <span className="font-display text-[16px] text-ink">
            {picked ? `${picked.name} · 景区` : '全部景区'}
          </span>
          <StateView state={parks.state} tone="warm">
            {(data) => <span className="text-[11.5px] text-ink-3">共 {data.total} 个</span>}
          </StateView>
        </div>
        <StateView
          state={parks.state}
          tone="warm"
          loadingText="正在读取景区…"
          isEmpty={(data) => data.items.length === 0}
          emptyText="没有匹配的景区，换个关键词或点「重置」试试"
          onRetry={parks.reload}
        >
          {(data) => (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {data.items.map((item) => {
                const status = PARK_STATUS[item.status]
                return (
                  <Link
                    key={item.id}
                    to={`/park/${item.id}`}
                    className="group flex flex-col rounded-2xl border border-sand bg-surface px-4 py-3.5 shadow-panel transition hover:border-amber/45"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <span className="font-display text-[16px] leading-tight text-ink">{item.name}</span>
                      <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[10.5px] ${TONE_CLASS[status?.tone ?? 'idle']}`}>
                        {status?.label ?? item.status}
                      </span>
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11.5px] text-ink-3">
                      {item.level && <span className="rounded bg-amber/12 px-1.5 py-0.5 text-amber-deep">{item.level}</span>}
                      <span>{item.destination_name ?? '未归属'}</span>
                      <span>· {item.attraction_count} 个景点</span>
                      {item.distance_m != null && <span className="text-steel-deep">· 距您 {formatDistance(item.distance_m)}</span>}
                    </div>
                    <p className="mt-2 line-clamp-2 text-[12.5px] leading-relaxed text-ink-2">{item.summary}</p>
                    <div className="mt-2.5 flex flex-wrap gap-1.5">
                      {item.tags.slice(0, 4).map((item) => (
                        <span key={item} className="rounded-full border border-sand bg-surface-2 px-2 py-0.5 text-[10.5px] text-ink-3">
                          {item}
                        </span>
                      ))}
                    </div>
                  </Link>
                )
              })}
            </div>
          )}
        </StateView>
      </section>

      {/* 数据面尚未铺开时的诚实提示 */}
      <EmptyState
        title="数据来自种子样本"
        desc="当前目的地与景区为演示用种子数据（3 个目的地 / 5 个景区 / 19 个景点），用于验证「通用化」链路；真实景区数据将在管理端接入后替换。"
        ticket="docs/09 G1"
      />
    </div>
  )
}
