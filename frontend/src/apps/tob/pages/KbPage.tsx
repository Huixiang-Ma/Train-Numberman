/**
 * 工单17 §2.2 · 知识库管理（批次 4，对应场景 S8）
 *
 * 为什么筛选放在前端：后端 `/kb` 只提供 limit/offset，没有关键词与模态参数。
 * 当前知识库量级（十位到百位）下，前端过滤能让筛选立即生效、不触发请求；
 * 数据量上去后应把 keyword / modality 下推到服务端分页（与 ParksPage 的判断一致）。
 *
 * 为什么编辑用抽屉而不是跳页：知识条目是"看一眼标题、改一句正文"的短操作，
 * 跳页会丢失列表的滚动位置与筛选条件。
 */
import { useEffect, useState } from 'react'
import { KB_MODALITY, api, type KbChunk } from '../../../api/client'
import PageHeader from '../../../shared/components/PageHeader'
import StateView from '../../../shared/components/StateView'
import { useAsync } from '../../../shared/hooks/useAsync'
import { apiErrorMessage } from '../../../shared/utils/error'
import { TONE_CLASS } from '../../../shared/utils/tone'

const PAGE_SIZE = 20

/** 可选的模态取值，与后端 services/kb.py 的 TEXT_MODALITIES / MEDIA_MODALITIES 对齐 */
const MODALITIES = ['text', 'image', 'video', 'audio']

export default function KbPage() {
  const [offset, setOffset] = useState(0)
  const [draft, setDraft] = useState('')
  const [keyword, setKeyword] = useState('')
  const [modality, setModality] = useState('')
  const [editing, setEditing] = useState<KbChunk | null>(null)
  const [creating, setCreating] = useState(false)
  const [notice, setNotice] = useState('')

  const list = useAsync(() => api.kbList({ limit: PAGE_SIZE, offset }), String(offset))

  // 筛选条件变化时回到第一页：否则会停在一个"过滤后为空"的页码上，
  // 用户看到空列表却不知道是筛没了还是本来就没有。
  useEffect(() => {
    setOffset(0)
  }, [keyword, modality])

  const reload = () => list.reload()

  return (
    <div>
      <PageHeader
        tone="cool"
        title="知识库管理"
        desc="多模态知识条目（工单17 §2.2）· 写入需运营及以上角色，检索侧对游客端生效"
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
              className="rounded-lg bg-steel px-3.5 py-1.5 text-[12.5px] font-medium text-white"
            >
              新增条目
            </button>
          </>
        }
      />

      {notice && (
        <div className="mb-3 rounded-lg border border-steel/35 bg-steel/10 px-3.5 py-2 text-[12.5px] text-steel-deep">
          {notice}
        </div>
      )}

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
            placeholder="搜索标题、正文或来源…"
            className="min-w-0 flex-1 rounded-lg border border-cool-line bg-cool-bg px-3 py-2 text-[12.5px] text-cool-ink outline-none placeholder:text-cool-ink-4 focus:border-steel/50"
          />
          <button type="submit" className="rounded-lg bg-steel px-3.5 py-2 text-[12.5px] text-white">
            搜索
          </button>
        </form>

        <label className="flex items-center gap-1.5 text-[12px] text-cool-ink-3">
          模态
          <select
            value={modality}
            onChange={(event) => setModality(event.target.value)}
            className="rounded-lg border border-cool-line bg-cool-bg px-2 py-2 text-[12.5px] text-cool-ink outline-none focus:border-steel/50"
          >
            <option value="">全部</option>
            {MODALITIES.map((item) => (
              <option key={item} value={item}>
                {KB_MODALITY[item]?.label ?? item}
              </option>
            ))}
          </select>
        </label>

        {(keyword || modality) && (
          <button
            onClick={() => {
              setDraft('')
              setKeyword('')
              setModality('')
            }}
            className="rounded-lg border border-cool-line bg-cool-surface px-3 py-2 text-[12.5px] text-cool-ink-3"
          >
            重置
          </button>
        )}
      </div>

      <StateView
        state={list.state}
        tone="cool"
        loadingText="正在读取知识条目…"
        isEmpty={(data) => data.items.length === 0}
        emptyText="知识库还没有条目，点右上角「新增条目」或上传文档开始构建"
        onRetry={reload}
      >
        {(data) => {
          const needle = keyword.toLowerCase()
          const rows = data.items.filter((item) => {
            if (modality && item.modality !== modality) return false
            if (!needle) return true
            return (
              item.title.toLowerCase().includes(needle) ||
              item.content.toLowerCase().includes(needle) ||
              item.source.toLowerCase().includes(needle)
            )
          })

          const from = data.total === 0 ? 0 : offset + 1
          const to = offset + data.items.length

          return (
            <div className="flex flex-col gap-4">
              <div className="flex flex-wrap items-center justify-between gap-2 text-[11.5px] text-cool-ink-3">
                <span>
                  共 {data.total} 条，当前显示 {from}–{to}
                  {rows.length !== data.items.length && ` · 本页筛选后 ${rows.length} 条`}
                </span>
                <span className="text-cool-ink-4">筛选仅作用于当前页，跨页筛选需后端支持关键词参数</span>
              </div>

              {rows.length === 0 ? (
                <div className="rounded-xl border border-dashed border-cool-line bg-cool-surface px-4 py-8 text-center text-[13px] text-cool-ink-3">
                  当前页没有匹配的条目
                </div>
              ) : (
                <div className="overflow-hidden rounded-xl border border-cool-line bg-cool-surface shadow-console">
                  <div className="overflow-x-auto">
                    <table className="w-full border-collapse text-[12.5px]">
                      <thead>
                        <tr className="bg-cool-surface-2 text-left text-cool-ink-3">
                          <th className="px-3.5 py-2.5 font-medium">标题</th>
                          <th className="px-3.5 py-2.5 font-medium">模态</th>
                          <th className="px-3.5 py-2.5 font-medium">标签</th>
                          <th className="px-3.5 py-2.5 font-medium">来源</th>
                          <th className="px-3.5 py-2.5 text-right font-medium">操作</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((item) => {
                          const tone = KB_MODALITY[item.modality]
                          return (
                            <tr key={item.id} className="border-t border-cool-line hover:bg-cool-surface-2/60">
                              <td className="px-3.5 py-2.5">
                                <div className="font-medium text-cool-ink">{item.title || '（无标题）'}</div>
                                <div className="mt-0.5 max-w-[420px] truncate text-[11.5px] text-cool-ink-3" title={item.content}>
                                  {item.content}
                                </div>
                              </td>
                              <td className="px-3.5 py-2.5">
                                <span
                                  className={`rounded-full border px-2 py-0.5 text-[10.5px] ${TONE_CLASS[tone?.tone ?? 'idle']}`}
                                >
                                  {tone?.label ?? item.modality}
                                </span>
                              </td>
                              <td className="px-3.5 py-2.5">
                                <div className="flex flex-wrap gap-1">
                                  {item.tags.length === 0 ? (
                                    <span className="text-cool-ink-4">—</span>
                                  ) : (
                                    item.tags.slice(0, 3).map((tag) => (
                                      <span
                                        key={tag}
                                        className="rounded border border-cool-line bg-cool-surface-2 px-1.5 py-0.5 text-[10.5px] text-cool-ink-3"
                                      >
                                        {tag}
                                      </span>
                                    ))
                                  )}
                                  {item.tags.length > 3 && (
                                    <span className="text-[10.5px] text-cool-ink-4">+{item.tags.length - 3}</span>
                                  )}
                                </div>
                              </td>
                              <td className="px-3.5 py-2.5 text-cool-ink-3">{item.source || '—'}</td>
                              <td className="px-3.5 py-2.5 text-right">
                                <button
                                  onClick={() => setEditing(item)}
                                  className="rounded-lg border border-cool-line bg-cool-surface px-2.5 py-1 text-[11.5px] text-cool-ink-2 hover:border-steel/40 hover:text-steel-deep"
                                >
                                  编辑
                                </button>
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* 分页 */}
              <div className="flex items-center justify-between gap-2">
                <button
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                  className="rounded-lg border border-cool-line bg-cool-surface px-3 py-1.5 text-[12.5px] text-cool-ink-2 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  上一页
                </button>
                <span className="text-[12px] text-cool-ink-3">
                  第 {Math.floor(offset / PAGE_SIZE) + 1} / {Math.max(1, Math.ceil(data.total / PAGE_SIZE))} 页
                </span>
                <button
                  disabled={to >= data.total}
                  onClick={() => setOffset(offset + PAGE_SIZE)}
                  className="rounded-lg border border-cool-line bg-cool-surface px-3 py-1.5 text-[12.5px] text-cool-ink-2 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  下一页
                </button>
              </div>
            </div>
          )
        }}
      </StateView>

      {editing && (
        <KbEditor
          chunk={editing}
          onClose={() => setEditing(null)}
          onDone={(message) => {
            setEditing(null)
            setNotice(message)
            reload()
          }}
        />
      )}

      {creating && (
        <KbCreator
          onClose={() => setCreating(false)}
          onDone={(message) => {
            setCreating(false)
            setNotice(message)
            setOffset(0)
            reload()
          }}
        />
      )}
    </div>
  )
}

// ---------------------------------------------------------------- 编辑抽屉

function KbEditor({
  chunk,
  onClose,
  onDone,
}: {
  chunk: KbChunk
  onClose: () => void
  onDone: (message: string) => void
}) {
  const [title, setTitle] = useState(chunk.title)
  const [content, setContent] = useState(chunk.content)
  const [source, setSource] = useState(chunk.source)
  const [tags, setTags] = useState(chunk.tags.join('，'))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const save = async () => {
    setBusy(true)
    setError('')
    try {
      await api.kbUpdate(chunk.id, {
        title,
        content,
        source,
        // 标签按中英文逗号与顿号切分，容忍运营的输入习惯
        tags: tags
          .split(/[,，、]/)
          .map((item) => item.trim())
          .filter(Boolean),
      })
      onDone(`已保存「${title || chunk.title}」`)
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    if (!window.confirm(`确认删除「${chunk.title || chunk.id}」？该操作会同时移除其向量索引。`)) return
    setBusy(true)
    setError('')
    try {
      await api.kbDelete(chunk.id)
      onDone(`已删除「${chunk.title || chunk.id}」`)
    } catch (err) {
      setError(apiErrorMessage(err))
      setBusy(false)
    }
  }

  return (
    <Drawer title="编辑知识条目" onClose={onClose}>
      <Field label="标题">
        <input value={title} onChange={(event) => setTitle(event.target.value)} className={INPUT} />
      </Field>
      <Field label="正文">
        <textarea
          value={content}
          onChange={(event) => setContent(event.target.value)}
          rows={8}
          className={`${INPUT} resize-y leading-relaxed`}
        />
      </Field>
      <Field label="标签" hint="逗号分隔，用于检索与筛选">
        <input value={tags} onChange={(event) => setTags(event.target.value)} className={INPUT} placeholder="历史，建筑" />
      </Field>
      <Field label="来源" hint="权威来源可提升检索权重（工单17 §2.5）">
        <input value={source} onChange={(event) => setSource(event.target.value)} className={INPUT} />
      </Field>

      <div className="mt-1 text-[11.5px] text-cool-ink-4">
        条目 ID <code className="text-cool-ink-3">{chunk.id}</code> · 模态{' '}
        {KB_MODALITY[chunk.modality]?.label ?? chunk.modality}（模态与媒体地址不在本抽屉修改）
      </div>

      {error && (
        <div className="mt-3 rounded-lg border border-clay/45 bg-clay/12 px-3 py-2 text-[12.5px] text-clay-deep">
          {error}
        </div>
      )}

      <div className="mt-4 flex items-center justify-between gap-2">
        <button
          onClick={remove}
          disabled={busy}
          className="rounded-lg border border-clay/45 bg-clay/12 px-3 py-2 text-[12.5px] text-clay-deep disabled:opacity-50"
        >
          删除
        </button>
        <div className="flex gap-2">
          <button
            onClick={onClose}
            className="rounded-lg border border-cool-line bg-cool-surface px-3.5 py-2 text-[12.5px] text-cool-ink-3"
          >
            取消
          </button>
          <button
            onClick={save}
            disabled={busy}
            className="rounded-lg bg-steel px-3.5 py-2 text-[12.5px] font-medium text-white disabled:opacity-50"
          >
            {busy ? '保存中…' : '保存'}
          </button>
        </div>
      </div>
    </Drawer>
  )
}

// ---------------------------------------------------------------- 新增条目

function KbCreator({ onClose, onDone }: { onClose: () => void; onDone: (message: string) => void }) {
  const [documentTitle, setDocumentTitle] = useState('')
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [tags, setTags] = useState('')
  const [source, setSource] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const submit = async () => {
    if (!content.trim()) {
      setError('正文不能为空')
      return
    }
    setBusy(true)
    setError('')
    try {
      const result = await api.kbIngest({
        document_title: documentTitle || title,
        source,
        chunks: [
          {
            title: title || documentTitle || '未命名条目',
            content: content.trim(),
            modality: 'text',
            tags: tags
              .split(/[,，、]/)
              .map((item) => item.trim())
              .filter(Boolean),
            source,
          },
        ],
      })
      onDone(`入库完成：新增 ${result.ingested} 条（文本索引 ${result.text}）`)
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const upload = async (file: File) => {
    setBusy(true)
    setError('')
    try {
      const form = new FormData()
      form.append('file', file)
      form.append('title', documentTitle || file.name)
      form.append('tags', tags)
      form.append('source', source)
      const task = await api.kbIngestFile(form)
      // 这是异步任务：后端入 MinIO 后交 Celery 解析分块，本页拿不到即时结果
      onDone(`文档已提交解析（任务 ${task.task_id.slice(0, 8)}…），分块入库完成后刷新可见`)
    } catch (err) {
      setError(apiErrorMessage(err))
      setBusy(false)
    }
  }

  return (
    <Drawer title="新增知识条目" onClose={onClose}>
      <Field label="所属文档" hint="同属一份资料的条目填同一个文档名，便于回溯（可留空）">
        <input
          value={documentTitle}
          onChange={(event) => setDocumentTitle(event.target.value)}
          className={INPUT}
          placeholder="瘦西湖志 · 桥梁卷"
        />
      </Field>
      <Field label="条目标题">
        <input value={title} onChange={(event) => setTitle(event.target.value)} className={INPUT} placeholder="五亭桥" />
      </Field>
      <Field label="正文" hint="这段文字会同时写入文本向量与图文向量索引">
        <textarea
          value={content}
          onChange={(event) => setContent(event.target.value)}
          rows={8}
          className={`${INPUT} resize-y leading-relaxed`}
          placeholder="五亭桥又名莲花桥，清乾隆二十二年建…"
        />
      </Field>
      <Field label="标签">
        <input value={tags} onChange={(event) => setTags(event.target.value)} className={INPUT} placeholder="清代，桥梁" />
      </Field>
      <Field label="来源">
        <input value={source} onChange={(event) => setSource(event.target.value)} className={INPUT} placeholder="景区志 · 官方" />
      </Field>

      <div className="mt-1 rounded-lg border border-dashed border-cool-line bg-cool-bg px-3 py-2.5">
        <div className="text-[12px] text-cool-ink-3">或上传文档批量入库</div>
        <input
          type="file"
          accept=".txt,.md,.pdf,.docx,.xlsx,.csv,.doc"
          disabled={busy}
          onChange={(event) => {
            const file = event.target.files?.[0]
            if (file) void upload(file)
            event.target.value = ''
          }}
          className="mt-2 w-full text-[11.5px] text-cool-ink-3 file:mr-2 file:rounded-lg file:border file:border-cool-line file:bg-cool-surface file:px-2.5 file:py-1 file:text-[11.5px] file:text-cool-ink-2"
        />
        <div className="mt-1.5 text-[11px] text-cool-ink-4">
          上传走异步解析（Celery），提交后需刷新列表查看结果
        </div>
      </div>

      {error && (
        <div className="mt-3 rounded-lg border border-clay/45 bg-clay/12 px-3 py-2 text-[12.5px] text-clay-deep">
          {error}
        </div>
      )}

      <div className="mt-4 flex justify-end gap-2">
        <button
          onClick={onClose}
          className="rounded-lg border border-cool-line bg-cool-surface px-3.5 py-2 text-[12.5px] text-cool-ink-3"
        >
          取消
        </button>
        <button
          onClick={submit}
          disabled={busy}
          className="rounded-lg bg-steel px-3.5 py-2 text-[12.5px] font-medium text-white disabled:opacity-50"
        >
          {busy ? '提交中…' : '入库'}
        </button>
      </div>
    </Drawer>
  )
}

// ---------------------------------------------------------------- 共用件

const INPUT =
  'w-full rounded-lg border border-cool-line bg-cool-bg px-3 py-2 text-[12.5px] text-cool-ink outline-none placeholder:text-cool-ink-4 focus:border-steel/50'

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="mb-3 block">
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <span className="text-[12px] text-cool-ink-3">{label}</span>
        {hint && <span className="text-[11px] text-cool-ink-4">{hint}</span>}
      </div>
      {children}
    </label>
  )
}

function Drawer({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-cool-ink/25" onClick={onClose}>
      <div
        className="h-full w-full max-w-[520px] overflow-y-auto border-l border-cool-line bg-cool-surface p-5 shadow-console"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="text-[15px] font-semibold text-cool-ink">{title}</h2>
          <button
            onClick={onClose}
            className="rounded-lg border border-cool-line bg-cool-surface px-2.5 py-1 text-[12px] text-cool-ink-3"
          >
            关闭
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}
