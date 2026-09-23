/**
 * 工单16 §2.2 · 数据查询（批次 6，对应场景 S8）
 *
 * **为什么不接自然语言问数**：工单原文是"数据查询能力"，很容易被理解成"输入一句话生成 SQL"。
 * 但那需要 NL→SQL 组件，本项目没有；用关键词硬匹配去凑，会产出**看起来能跑、结果却不对**
 * 的查询 —— 运营据此做决策比拿不到数据更危险。因此这里提供确定性的人工筛选，
 * 并在页面上写明它不解析自然语言，同时把"问知识库"的入口单独给出去（那才是数字人的强项）。
 *
 * 导出走前端 CSV：数据已在本页，回服务端再生成一遍是多余往返；
 * 加 BOM 是因为 Excel 打开无 BOM 的 UTF-8 CSV 会把中文显示成乱码。
 */
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, datasetToCsv, type DatasetData } from '../../../api/client'
import PageHeader from '../../../shared/components/PageHeader'
import StateView from '../../../shared/components/StateView'
import { useAsync } from '../../../shared/hooks/useAsync'

const LIMIT_OPTIONS = [50, 200, 500, 1000]

export default function QueryPage() {
  const [dataset, setDataset] = useState('parks')
  const [limit, setLimit] = useState(200)
  const [draft, setDraft] = useState('')
  const [keyword, setKeyword] = useState('')
  const [notice, setNotice] = useState('')

  const datasets = useAsync(() => api.analyticsDatasets(), '')
  const data = useAsync(() => api.analyticsDataset(dataset, limit), `${dataset}|${limit}`)

  // 筛选在前端做：数据集已经取回本地，再回服务端过滤会多一次往返且无法即时反馈
  const filtered = useMemo<(string | number)[][]>(() => {
    if (data.state.kind !== 'ready') return []
    const needle = keyword.trim().toLowerCase()
    if (!needle) return data.state.data.rows
    return data.state.data.rows.filter((row) => row.some((cell) => String(cell).toLowerCase().includes(needle)))
  }, [data.state, keyword])

  const exportCsv = (payload: DatasetData) => {
    const blob = new Blob([datasetToCsv({ ...payload, rows: filtered })], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    // 文件名带日期：运营导出多份后要靠它区分
    anchor.download = `${payload.name}-${new Date().toISOString().slice(0, 10)}.csv`
    anchor.click()
    URL.revokeObjectURL(url)
    setNotice(`已导出 ${filtered.length} 行到 ${anchor.download}`)
  }

  return (
    <div>
      <PageHeader
        tone="cool"
        title="数据查询"
        desc="按数据集浏览与导出运营数据（工单16 §2.2 · S8）· 确定性筛选，不解析自然语言"
        extra={
          <Link
            to="/admin/commands"
            className="rounded-lg border border-cool-line bg-cool-surface px-3 py-1.5 text-[12.5px] text-cool-ink-2 hover:border-steel/40 hover:text-steel-deep"
          >
            去问运营助理
          </Link>
        }
      />

      <div className="mb-3 rounded-lg border border-amber/40 bg-amber/10 px-3.5 py-2.5 text-[11.5px] leading-relaxed text-amber-deep">
        本页<strong>不解析自然语言</strong>。NL 转 SQL 需要专门组件，本项目未引入；
        用关键词硬匹配会生成看似可用但结果不对的查询，运营据此决策风险更高。
        需要"用一句话问"的场景，请到「快捷指令工作台」问运营助理（它答的是知识库，不是运营数据库）。
      </div>

      {notice && (
        <div className="mb-3 rounded-lg border border-steel/35 bg-steel/10 px-3.5 py-2 text-[12.5px] text-steel-deep">
          {notice}
        </div>
      )}

      {/* 选择与筛选 */}
      <div className="mb-4 flex flex-wrap items-center gap-2 rounded-xl border border-cool-line bg-cool-surface px-3.5 py-3 shadow-console">
        <label className="flex items-center gap-1.5 text-[12px] text-cool-ink-3">
          数据集
          <select
            value={dataset}
            onChange={(event) => {
              setDataset(event.target.value)
              setKeyword('')
              setDraft('')
            }}
            className="min-w-[150px] rounded-lg border border-cool-line bg-cool-bg px-2 py-2 text-[12.5px] text-cool-ink outline-none focus:border-steel/50"
          >
            {datasets.state.kind === 'ready' &&
              datasets.state.data.items.map((item) => (
                <option key={item.name} value={item.name}>
                  {item.label}
                </option>
              ))}
          </select>
        </label>

        <form
          className="flex min-w-[190px] flex-1 gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            setKeyword(draft)
          }}
        >
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="在当前结果中筛选（任意列包含）…"
            className="min-w-0 flex-1 rounded-lg border border-cool-line bg-cool-bg px-3 py-2 text-[12.5px] text-cool-ink outline-none placeholder:text-cool-ink-4 focus:border-steel/50"
          />
          <button type="submit" className="rounded-lg bg-steel px-3.5 py-2 text-[12.5px] text-white">
            筛选
          </button>
        </form>

        <label className="flex items-center gap-1.5 text-[12px] text-cool-ink-3">
          条数
          <select
            value={limit}
            onChange={(event) => setLimit(Number(event.target.value))}
            className="rounded-lg border border-cool-line bg-cool-bg px-2 py-2 text-[12.5px] text-cool-ink outline-none focus:border-steel/50"
          >
            {LIMIT_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>

        {(keyword || draft) && (
          <button
            onClick={() => {
              setDraft('')
              setKeyword('')
            }}
            className="rounded-lg border border-cool-line bg-cool-surface px-3 py-2 text-[12.5px] text-cool-ink-3"
          >
            重置筛选
          </button>
        )}
      </div>

      <StateView
        state={data.state}
        tone="cool"
        loadingText="正在读取数据集…"
        isEmpty={(payload) => payload.rows.length === 0}
        emptyText="该数据集暂无记录"
        onRetry={data.reload}
      >
        {(payload) => (
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center justify-between gap-2 text-[11.5px] text-cool-ink-3">
              <span>
                {payload.label} · 共 {payload.rows.length} 行
                {filtered.length !== payload.rows.length && ` · 筛选后 ${filtered.length} 行`}
              </span>
              <div className="flex flex-wrap items-center gap-3">
                <span className="text-cool-ink-4">上限 {limit} 行，需更多请提高条数</span>
                <button
                  onClick={() => exportCsv(payload)}
                  disabled={filtered.length === 0}
                  className="rounded-lg border border-cool-line bg-cool-surface px-3 py-1.5 text-[12px] text-cool-ink-2 hover:border-steel/40 disabled:opacity-40"
                >
                  导出 CSV（{filtered.length} 行）
                </button>
              </div>
            </div>

            {filtered.length === 0 ? (
              <div className="rounded-xl border border-dashed border-cool-line bg-cool-surface px-4 py-8 text-center text-[13px] text-cool-ink-3">
                没有匹配「{keyword}」的行
              </div>
            ) : (
              <div className="overflow-hidden rounded-xl border border-cool-line bg-cool-surface shadow-console">
                <div className="overflow-x-auto">
                  <table className="w-full border-collapse text-[12.5px]">
                    <thead>
                      <tr className="bg-cool-surface-2 text-left text-cool-ink-3">
                        {payload.columns.map((column) => (
                          <th key={column} className="whitespace-nowrap px-3.5 py-2.5 font-medium">
                            {column}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {filtered.map((row, rowIndex) => (
                        <tr key={rowIndex} className="border-t border-cool-line hover:bg-cool-surface-2/60">
                          {row.map((cell, cellIndex) => (
                            <td
                              key={cellIndex}
                              className={`px-3.5 py-2 ${
                                typeof cell === 'number' ? 'text-right tabular-nums text-cool-ink-2' : 'text-cool-ink-2'
                              }`}
                            >
                              {String(cell)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}
      </StateView>
    </div>
  )
}
