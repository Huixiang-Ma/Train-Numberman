/**
 * 工单16 §2.1 · 景区管理者 / 运营人员 —— 控制台总览
 * 工单16-20 延伸 · 平台化双端重构（批次 0）
 *
 * 数据源为现有接口 /readyz 与 /stack，本批次零后端改动即可有真实内容。
 * 字段解释走 shared/utils/health 的容错逻辑，后端新增检查项无需改前端。
 */
import { useCallback, useEffect, useState } from 'react'
import { api } from '../../../api/client'
import PageHeader from '../../../shared/components/PageHeader'
import { TONE_CLASS, TONE_LABEL, collectChecks, formatValue, inferTone, type HealthCheck } from '../../../shared/utils/health'

type LoadState =
  | { kind: 'loading' }
  | { kind: 'ready'; checks: HealthCheck[]; stack: [string, unknown][] }
  | { kind: 'error'; message: string }

export default function OverviewPage() {
  const [state, setState] = useState<LoadState>({ kind: 'loading' })

  const load = useCallback(async () => {
    setState({ kind: 'loading' })
    try {
      const [ready, stack] = await Promise.all([api.readyz(), api.stack()])
      // 必须用 collectChecks 下钻到 services：/readyz 顶层只有 work_order/stack/services
      // 三个键，直接 Object.entries 会把整个 services 塌成一行，四个组件状态全都看不见。
      setState({ kind: 'ready', checks: collectChecks(ready), stack: Object.entries(stack) })
    } catch (error) {
      setState({ kind: 'error', message: error instanceof Error ? error.message : String(error) })
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <div>
      <PageHeader
        tone="cool"
        title="控制台总览"
        desc="后端组件健康状态与技术栈实际接入情况（数据源 /readyz · /stack）"
        extra={
          <button
            onClick={() => void load()}
            className="rounded-lg border border-cool-line bg-cool-surface px-3 py-1.5 text-[12.5px] text-cool-ink-2 hover:border-steel/40 hover:text-steel-deep"
          >
            重新检测
          </button>
        }
      />

      {state.kind === 'loading' && <div className="text-[13px] text-cool-ink-3">检测中…</div>}

      {state.kind === 'error' && (
        <div className="rounded-xl border border-clay/40 bg-clay/10 px-4 py-3 text-[13px] text-clay-deep">
          后端未就绪：{state.message}
          <div className="mt-1 text-[12px] text-clay">
            请在 backend 目录启动 `python -m uvicorn app.main:app --port 8100`，并确认 Docker 依赖容器已运行。
          </div>
        </div>
      )}

      {state.kind === 'ready' && (
        <div className="flex flex-col gap-5">
          <section>
            <div className="mb-2 text-[13px] font-medium text-cool-ink">组件健康</div>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
              {state.checks.map(({ name, value }) => {
                const tone = inferTone(value)
                return (
                  <div
                    key={name}
                    className="flex items-center justify-between gap-3 rounded-xl border border-cool-line bg-cool-surface px-3.5 py-2.5 shadow-console"
                  >
                    <span className="truncate text-[12.5px] text-cool-ink-2" title={name}>
                      {name}
                    </span>
                    <span className="flex shrink-0 items-center gap-2">
                      <span className="max-w-[140px] truncate text-[12px] text-cool-ink-3">{formatValue(value)}</span>
                      <span className={`rounded-full border px-2 py-0.5 text-[10.5px] ${TONE_CLASS[tone]}`}>
                        {TONE_LABEL[tone]}
                      </span>
                    </span>
                  </div>
                )
              })}
            </div>
          </section>

          <section>
            <div className="mb-2 text-[13px] font-medium text-cool-ink">技术栈接入</div>
            <div className="overflow-hidden rounded-xl border border-cool-line bg-cool-surface shadow-console">
              <table className="w-full border-collapse text-[12.5px]">
                <thead>
                  <tr className="bg-cool-surface-2 text-cool-ink-3">
                    <th className="px-3.5 py-2 text-left font-medium">项</th>
                    <th className="px-3.5 py-2 text-left font-medium">实际值</th>
                  </tr>
                </thead>
                <tbody>
                  {state.stack.map(([key, value]) => (
                    <tr key={key} className="border-t border-cool-line">
                      <td className="px-3.5 py-2 text-cool-ink-2">{key}</td>
                      <td className="px-3.5 py-2 text-cool-ink">{formatValue(value)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      )}
    </div>
  )
}
