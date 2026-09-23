/**
 * 工单16 §2.2 · 快捷指令工作台（批次 6，对应场景 S9）
 *
 * 五个指令直接对应工单16 §2.2 列出的五项：资源挖掘 / 场景创意 / 文化创新 /
 * 数字营销 / 效益提升。每个指令是一段**带景区上下文的提示模板**，
 * 而不是一个隐藏的专用模型 —— 运营点开后能看到实际发出去的问句，
 * 也能改完再发。这是"可解释"与"黑盒按钮"的区别。
 *
 * 运营助理复用数字人对话链路（/dialog）：同一套知识与检索，换了使用场景，
 * 这正是 docs/09 §3.3「数字人是跨模块能力」的具体体现。
 * 因此它答的是**知识库内容**，不产出结构化报表；需要报表请用「数据查询」。
 */
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type DialogResult } from '../../../api/client'
import PageHeader from '../../../shared/components/PageHeader'
import { useAsync } from '../../../shared/hooks/useAsync'
import { apiErrorMessage } from '../../../shared/utils/error'

type Command = {
  key: string
  label: string
  glyph: string
  desc: string
  /** {park} 会被替换成所选景区名 */
  template: string
}

/** 五项指令取自工单16 §2.2 的「快捷指令」清单，顺序与工单一致 */
const COMMANDS: Command[] = [
  {
    key: 'resource',
    label: '资源挖掘',
    glyph: '⛏',
    desc: '盘点景区可挖掘的文化资源，按可开发程度排序',
    template: '请盘点{park}可挖掘的文化与自然资源，逐项说明它目前是否已被利用，并按可开发程度排序。',
  },
  {
    key: 'scene',
    label: '场景创意',
    glyph: '✦',
    desc: '设计可落地的沉浸式体验场景',
    template: '请为{park}设计 3 个可落地的沉浸式体验场景，每个说明：目标人群、场地要求、所需技术、预期停留时长。',
  },
  {
    key: 'culture',
    label: '文化创新',
    glyph: '❖',
    desc: '把历史文化元素转译为现代传播语言',
    template: '请把{park}的历史文化元素转译为面向年轻游客的现代传播语言，给出 5 个具体方向，每个附一句可直接使用的文案。',
  },
  {
    key: 'marketing',
    label: '数字营销',
    glyph: '◈',
    desc: '设计数字营销方案的渠道与节奏',
    template: '请为{park}设计一套数字营销方案，包含目标人群、渠道选择、内容形式与发布节奏，并说明每项的衡量指标。',
  },
  {
    key: 'benefit',
    label: '效益提升',
    glyph: '▲',
    desc: '分析运营瓶颈并给出可量化建议',
    template: '请分析{park}当前的运营瓶颈（客流、动线、服务、二次消费四个角度），给出可量化的效益提升建议，并标注哪些需要额外投入。',
  },
]

export default function CommandsPage() {
  const [parkId, setParkId] = useState('')
  const [prompt, setPrompt] = useState('')
  const [result, setResult] = useState<{ command: string; question: string; data: DialogResult } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const parks = useAsync(() => api.parks({ limit: 200 }), '')
  const parkName =
    parks.state.kind === 'ready' ? (parks.state.data.items.find((item) => item.id === parkId)?.name ?? '{景区}') : '{景区}'

  const run = async (commandLabel: string, text: string) => {
    const question = text.trim()
    if (!question) {
      setError('请输入要交给助理的问题')
      return
    }
    setBusy(true)
    setError('')
    try {
      const data = await api.assistant(question)
      setResult({ command: commandLabel, question, data })
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <PageHeader
        tone="cool"
        title="快捷指令工作台"
        desc="工单16 §2.2 的五项运营指令 · 由数字人担任运营助理（同一套知识检索，换了使用场景）"
        extra={
          <Link
            to="/admin/content"
            className="rounded-lg border border-cool-line bg-cool-surface px-3 py-1.5 text-[12.5px] text-cool-ink-2 hover:border-steel/40 hover:text-steel-deep"
          >
            去内容生产（PPT / 流程图）
          </Link>
        }
      />

      <div className="mb-3 rounded-lg border border-cool-line bg-cool-surface px-3.5 py-2.5 text-[11.5px] leading-relaxed text-cool-ink-3">
        助理回答来自<strong className="text-cool-ink-2">知识库检索</strong>（含引文出处），
        因此适合做素材梳理与方案起草，<strong className="text-cool-ink-2">不产出结构化经营报表</strong>；
        需要数字请用「数据查询」或「经营分析」。指令模板可自由修改后再发送。
      </div>

      {/* 景区上下文 */}
      <div className="mb-4 flex flex-wrap items-center gap-2 rounded-xl border border-cool-line bg-cool-surface px-3.5 py-3 shadow-console">
        <label className="flex items-center gap-1.5 text-[12px] text-cool-ink-3">
          工作对象
          <select
            value={parkId}
            onChange={(event) => setParkId(event.target.value)}
            className="min-w-[170px] rounded-lg border border-cool-line bg-cool-bg px-2 py-2 text-[12.5px] text-cool-ink outline-none focus:border-steel/50"
          >
            <option value="">不指定（用「景区」占位）</option>
            {parks.state.kind === 'ready' &&
              parks.state.data.items.map((park) => (
                <option key={park.id} value={park.id}>
                  {park.name}
                </option>
              ))}
          </select>
        </label>
        <span className="text-[11.5px] text-cool-ink-4">
          选定后会把景区名填进指令模板，让助理的回答落到具体对象上
        </span>
      </div>

      {/* 五个指令 */}
      <section className="mb-4">
        <h2 className="mb-2.5 text-[13px] font-medium text-cool-ink">快捷指令</h2>
        <div className="grid grid-cols-1 gap-2.5 md:grid-cols-2 xl:grid-cols-3">
          {COMMANDS.map((command) => {
            // 用 split/join 而不是 replaceAll：后者的 lib 要求为 ES2021，
            // 而本项目 tsconfig 的 lib 目标更低，直接用会编译不过。
            const filled = command.template.split('{park}').join(parkName)
            return (
              <div key={command.key} className="flex flex-col rounded-xl border border-cool-line bg-cool-surface p-3.5 shadow-console">
                <div className="flex items-center gap-2">
                  <span className="grid h-7 w-7 place-items-center rounded-lg bg-steel/12 text-[14px] text-steel-deep">
                    {command.glyph}
                  </span>
                  <span className="text-[13px] font-medium text-cool-ink">{command.label}</span>
                </div>
                <p className="mt-2 text-[11.5px] leading-relaxed text-cool-ink-3">{command.desc}</p>
                <p className="mt-2 rounded-lg border border-cool-line bg-cool-bg px-2.5 py-2 text-[11px] leading-relaxed text-cool-ink-2">
                  {filled}
                </p>
                <div className="mt-2.5 flex gap-1.5">
                  <button
                    onClick={() => run(command.label, filled)}
                    disabled={busy}
                    className="rounded-lg bg-steel px-3 py-1.5 text-[11.5px] font-medium text-white disabled:opacity-50"
                  >
                    执行指令
                  </button>
                  <button
                    onClick={() => {
                      setPrompt(filled)
                      setResult(null)
                      setError('')
                    }}
                    className="rounded-lg border border-cool-line bg-cool-surface px-3 py-1.5 text-[11.5px] text-cool-ink-2 hover:border-steel/40"
                  >
                    先改再发
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      </section>

      {/* 自由提问 */}
      <section className="mb-4 rounded-xl border border-cool-line bg-cool-surface p-4 shadow-console">
        <h2 className="mb-2.5 text-[13px] font-medium text-cool-ink">自由提问</h2>
        <textarea
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          rows={4}
          className="w-full resize-y rounded-lg border border-cool-line bg-cool-bg px-3 py-2 text-[12.5px] leading-relaxed text-cool-ink outline-none placeholder:text-cool-ink-4 focus:border-steel/50"
          placeholder="例如：把上面的资源挖掘结果整理成一份对外汇报的提纲"
        />
        {error && (
          <div className="mt-2.5 rounded-lg border border-clay/45 bg-clay/12 px-3 py-2 text-[12.5px] text-clay-deep">{error}</div>
        )}
        <div className="mt-3 flex justify-end">
          <button
            onClick={() => run('自由提问', prompt)}
            disabled={busy || !prompt.trim()}
            className="rounded-lg bg-steel px-4 py-2 text-[12.5px] font-medium text-white disabled:opacity-50"
          >
            {busy ? '助理处理中…' : '问运营助理'}
          </button>
        </div>
      </section>

      {/* 结果 */}
      {result && (
        <section className="rounded-xl border border-steel/35 bg-cool-surface p-4 shadow-console">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-[13px] font-medium text-cool-ink">
              助理答复 · <span className="text-steel-deep">{result.command}</span>
            </h2>
            <span className="text-[11px] text-cool-ink-4">
              工作流 {result.data.workflow} · 会话 {result.data.session_id?.slice(0, 8) ?? '—'}
            </span>
          </div>

          <div className="mt-2 rounded-lg border border-cool-line bg-cool-bg px-3 py-2">
            <div className="text-[11px] text-cool-ink-4">实际发送的问句</div>
            <p className="mt-0.5 text-[12px] leading-relaxed text-cool-ink-2">{result.question}</p>
          </div>

          <div className="mt-3 whitespace-pre-wrap text-[12.5px] leading-relaxed text-cool-ink">
            {result.data.answer_text || '（未返回内容）'}
          </div>

          {result.data.citations.length > 0 && (
            <div className="mt-3 border-t border-cool-line pt-3">
              <div className="mb-1.5 text-[11.5px] text-cool-ink-3">引用来源（{result.data.citations.length} 条）</div>
              <ul className="flex flex-col gap-1">
                {result.data.citations.map((item) => (
                  <li key={item.kb_id} className="flex items-baseline gap-2 text-[11.5px]">
                    <span className="truncate text-cool-ink-2">{item.title}</span>
                    <span className="shrink-0 text-cool-ink-4">
                      {item.source || '未标注来源'} · score {item.score}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {result.data.citations.length === 0 && (
            <div className="mt-3 rounded-lg border border-amber/40 bg-amber/10 px-3 py-2 text-[11.5px] leading-relaxed text-amber-deep">
              本次回答<strong>没有引用到知识库条目</strong>，说明该主题在知识库中尚无对应内容。
              这条问题会进入「游客需求洞察」的盲区清单，提示需要补充资料。
            </div>
          )}
        </section>
      )}
    </div>
  )
}
