/**
 * 工单16 §2.2 · 内容生产与发布（批次 4，对应场景 S8）
 *
 * 三条生产链路各自对应工单里的一个场景：
 *   - 参与攻略 / 流程图文（`/create/guide`）→ 工单19 §3「一键生成参与攻略、体验流程图」
 *   - 导览地图          （`/create/map`）  → 工单20 场景13「个性化地图可下载打印」
 *   - 活动回顾 PPT      （`/create/ppt`）  → 工单20 场景12「活动照片 → 回顾 PPT」
 *
 * 右侧产物库复用 `/create/assets`：产出即入库，刷新页面不丢，避免运营反复重跑生成。
 */
import { useState } from 'react'
import { api, assetUrl, type CreationAsset } from '../../../api/client'
import PageHeader from '../../../shared/components/PageHeader'
import StateView from '../../../shared/components/StateView'
import { useAsync } from '../../../shared/hooks/useAsync'
import { apiErrorMessage } from '../../../shared/utils/error'
import { TONE_CLASS } from '../../../shared/utils/tone'

type Tab = 'guide' | 'map' | 'ppt'

const TABS: { key: Tab; label: string; desc: string }[] = [
  { key: 'guide', label: '参与攻略与流程图', desc: '输入活动或兴趣，生成步骤攻略、流程图与可下载图片' },
  { key: 'map', label: '导览地图', desc: '按站名与顺序生成导览地图，坐标由后端按景点名补齐' },
  { key: 'ppt', label: '活动回顾 PPT', desc: '上传活动照片，生成封面 + 每图一页 + 结尾页的演示文稿' },
]

export default function ContentPage() {
  const [tab, setTab] = useState<Tab>('guide')
  const [notice, setNotice] = useState('')
  const assets = useAsync(() => api.createAssets(), '')

  const refresh = () => assets.reload()

  return (
    <div>
      <PageHeader
        tone="cool"
        title="内容生产与发布"
        desc="讲解词、攻略流程图、导览地图与回顾 PPT 的统一生产入口（工单16 §2.2 · S8）"
        extra={
          <button
            onClick={refresh}
            className="rounded-lg border border-cool-line bg-cool-surface px-3 py-1.5 text-[12.5px] text-cool-ink-2 hover:border-steel/40 hover:text-steel-deep"
          >
            刷新产物库
          </button>
        }
      />

      {notice && (
        <div className="mb-3 rounded-lg border border-steel/35 bg-steel/10 px-3.5 py-2 text-[12.5px] text-steel-deep">
          {notice}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
        {/* 生成面板 */}
        <div className="rounded-xl border border-cool-line bg-cool-surface p-4 shadow-console">
          <div className="scroll-x mb-4">
            {TABS.map((item) => (
              <button
                key={item.key}
                onClick={() => setTab(item.key)}
                className={`rounded-full border px-3 py-1.5 text-[12px] ${
                  tab === item.key
                    ? 'border-steel/45 bg-steel/10 font-medium text-steel-deep'
                    : 'border-cool-line bg-cool-surface-2 text-cool-ink-3'
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>

          <p className="mb-4 text-[11.5px] leading-relaxed text-cool-ink-3">{TABS.find((item) => item.key === tab)?.desc}</p>

          {tab === 'guide' && <GuideForm onDone={(message) => { setNotice(message); refresh() }} />}
          {tab === 'map' && <MapForm onDone={(message) => { setNotice(message); refresh() }} />}
          {tab === 'ppt' && <PptForm onDone={(message) => { setNotice(message); refresh() }} />}
        </div>

        {/* 产物库 */}
        <div>
          <StateView
            state={assets.state}
            tone="cool"
            loadingText="正在读取产物…"
            isEmpty={(data) => data.items.length === 0}
            emptyText="还没有生成过内容，左侧生成一次即可入库"
            onRetry={refresh}
          >
            {(data) => (
              <div className="flex flex-col gap-3">
                <div className="text-[11.5px] text-cool-ink-3">产物库 · 共 {data.total} 件（按创建时间倒序）</div>
                {data.items.map((asset) => (
                  <AssetCard key={asset.id} asset={asset} onShared={setNotice} />
                ))}
              </div>
            )}
          </StateView>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- 三个生成表单

function GuideForm({ onDone }: { onDone: (message: string) => void }) {
  const [activityName, setActivityName] = useState('')
  const [interests, setInterests] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<{ title: string; steps: string[]; guide_text: string; diagram_url: string | null } | null>(null)

  const submit = async () => {
    if (!activityName.trim() && !interests.trim()) {
      setError('活动名称与兴趣偏好至少填一项')
      return
    }
    setBusy(true)
    setError('')
    try {
      const data = await api.createGuide({
        activity_name: activityName.trim() || undefined,
        interests: interests
          .split(/[,，、]/)
          .map((item) => item.trim())
          .filter(Boolean),
      })
      setResult(data)
      onDone(`已生成「${data.title}」，产物已入库`)
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <Field label="活动 / 体验名称">
        <input value={activityName} onChange={(event) => setActivityName(event.target.value)} className={INPUT} placeholder="非遗漆扇手作体验" />
      </Field>
      <Field label="兴趣偏好" hint="逗号分隔">
        <input value={interests} onChange={(event) => setInterests(event.target.value)} className={INPUT} placeholder="亲子，手作，非遗" />
      </Field>

      {error && <ErrorBox text={error} />}

      <button onClick={submit} disabled={busy} className={PRIMARY}>
        {busy ? '生成中…' : '生成攻略与流程图'}
      </button>

      {result && (
        <div className="mt-4 rounded-lg border border-cool-line bg-cool-bg p-3">
          <div className="text-[12.5px] font-medium text-cool-ink">{result.title}</div>
          <ol className="mt-2 list-decimal space-y-1 pl-4 text-[12px] leading-relaxed text-cool-ink-2">
            {result.steps.map((step, index) => (
              <li key={index}>{step}</li>
            ))}
          </ol>
          {result.diagram_url && (
            <a
              href={assetUrl(result.diagram_url)}
              target="_blank"
              rel="noreferrer"
              className="mt-2.5 inline-block text-[11.5px] text-steel-deep underline"
            >
              查看流程图图片
            </a>
          )}
        </div>
      )}
    </div>
  )
}

function MapForm({ onDone }: { onDone: (message: string) => void }) {
  const [title, setTitle] = useState('瘦西湖半日游')
  const [subtitle, setSubtitle] = useState('')
  const [stops, setStops] = useState('五亭桥\n白塔\n二十四桥')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [asset, setAsset] = useState<CreationAsset | null>(null)

  const submit = async () => {
    const stops_ = stops
      .split('\n')
      .map((item) => item.trim())
      .filter(Boolean)
    if (stops_.length < 2) {
      setError('至少填两个站点（每行一个）')
      return
    }
    setBusy(true)
    setError('')
    try {
      const data = await api.createMap({
        title: title.trim() || undefined,
        subtitle: subtitle.trim() || undefined,
        stops: stops_.map((name, index) => ({ name, index: index + 1 })),
      })
      setAsset(data)
      onDone(`已生成导览地图「${data.title}」`)
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <Field label="地图标题">
        <input value={title} onChange={(event) => setTitle(event.target.value)} className={INPUT} />
      </Field>
      <Field label="副标题" hint="可留空">
        <input value={subtitle} onChange={(event) => setSubtitle(event.target.value)} className={INPUT} placeholder="推荐游览 2.5 小时" />
      </Field>
      <Field label="站点" hint="每行一个，顺序即游览顺序">
        <textarea value={stops} onChange={(event) => setStops(event.target.value)} rows={6} className={`${INPUT} resize-y leading-relaxed`} />
      </Field>

      {error && <ErrorBox text={error} />}

      <button onClick={submit} disabled={busy} className={PRIMARY}>
        {busy ? '生成中…' : '生成导览地图'}
      </button>

      {asset?.url && (
        <div className="mt-4">
          <img src={assetUrl(asset.url)} alt={asset.title} className="w-full rounded-lg border border-cool-line" />
          <a
            href={assetUrl(asset.url)}
            download
            className="mt-2 inline-block text-[11.5px] text-steel-deep underline"
          >
            下载地图（可打印）
          </a>
        </div>
      )}
    </div>
  )
}

function PptForm({ onDone }: { onDone: (message: string) => void }) {
  const [files, setFiles] = useState<File[]>([])
  const [title, setTitle] = useState('活动回顾')
  const [subtitle, setSubtitle] = useState('')
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [asset, setAsset] = useState<CreationAsset | null>(null)

  const submit = async () => {
    if (files.length === 0) {
      setError('请先选择活动照片')
      return
    }
    setBusy(true)
    setError('')
    try {
      const form = new FormData()
      files.forEach((file) => form.append('files', file))
      form.append('title', title)
      form.append('subtitle', subtitle)
      form.append('notes', notes)
      const data = await api.createPpt(form)
      setAsset(data)
      onDone(`已生成 PPT「${data.title}」`)
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <Field label="标题">
        <input value={title} onChange={(event) => setTitle(event.target.value)} className={INPUT} />
      </Field>
      <Field label="副标题" hint="可留空">
        <input value={subtitle} onChange={(event) => setSubtitle(event.target.value)} className={INPUT} />
      </Field>
      <Field label="活动照片" hint="可多选，每张照片对应一页">
        <input
          type="file"
          accept="image/*"
          multiple
          onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
          className="w-full text-[11.5px] text-cool-ink-3 file:mr-2 file:rounded-lg file:border file:border-cool-line file:bg-cool-surface file:px-2.5 file:py-1 file:text-[11.5px] file:text-cool-ink-2"
        />
      </Field>
      {files.length > 0 && <div className="mb-3 text-[11.5px] text-cool-ink-3">已选 {files.length} 张</div>}
      <Field label="每页备注" hint="每行对应一张照片，可留空">
        <textarea value={notes} onChange={(event) => setNotes(event.target.value)} rows={4} className={`${INPUT} resize-y leading-relaxed`} />
      </Field>

      {error && <ErrorBox text={error} />}

      <button onClick={submit} disabled={busy} className={PRIMARY}>
        {busy ? '生成中…' : '生成回顾 PPT'}
      </button>

      {asset?.url && (
        <a href={assetUrl(asset.url)} download className="mt-3 inline-block text-[11.5px] text-steel-deep underline">
          下载 {asset.mime.includes('presentation') ? '.pptx' : '文件'}
        </a>
      )}
    </div>
  )
}

// ---------------------------------------------------------------- 产物卡

function AssetCard({ asset, onShared }: { asset: CreationAsset; onShared: (message: string) => void }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const share = async () => {
    setBusy(true)
    setError('')
    try {
      const result = await api.share({ asset_id: asset.id, channel: 'link', title: asset.title })
      try {
        await navigator.clipboard.writeText(`${window.location.origin}${result.url}`)
        onShared(`分享链接已复制：${result.url}`)
      } catch {
        // 剪贴板在非安全上下文会被拒，这里如实提示链接本身而不是假装成功
        onShared(`分享链接已生成：${result.url}（浏览器未允许自动复制）`)
      }
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rounded-xl border border-cool-line bg-cool-surface p-3.5 shadow-console">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-[13px] font-medium text-cool-ink">{asset.title}</div>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-cool-ink-3">
            <span className={`rounded-full border px-2 py-0.5 ${TONE_CLASS[asset.status === 'success' ? 'ok' : 'warn']}`}>
              {asset.status === 'success' ? '已完成' : asset.status}
            </span>
            <span>{asset.kind}</span>
            {asset.model && <span className="truncate">{asset.model}</span>}
              {asset.size_bytes > 0 && <span>{(asset.size_bytes / 1024).toFixed(0)} KB</span>}
          </div>
        </div>
        <button
          onClick={share}
          disabled={busy}
          className="shrink-0 rounded-lg border border-cool-line bg-cool-surface px-2.5 py-1 text-[11.5px] text-cool-ink-2 hover:border-steel/40 hover:text-steel-deep disabled:opacity-50"
        >
          {busy ? '…' : '分享'}
        </button>
      </div>

      {asset.text_content && (
        <p className="mt-2.5 line-clamp-3 text-[11.5px] leading-relaxed text-cool-ink-2">{asset.text_content}</p>
      )}

      {asset.url && asset.mime.startsWith('image/') && (
        <img src={assetUrl(asset.url)} alt={asset.title} className="mt-2.5 max-h-[180px] w-full rounded-lg border border-cool-line object-cover" />
      )}

      {asset.url && (
        <a href={assetUrl(asset.url)} target="_blank" rel="noreferrer" className="mt-2 inline-block text-[11.5px] text-steel-deep underline">
          打开产物
        </a>
      )}

      {error && <ErrorBox text={error} />}
    </div>
  )
}

// ---------------------------------------------------------------- 共用件

const INPUT =
  'w-full rounded-lg border border-cool-line bg-cool-bg px-3 py-2 text-[12.5px] text-cool-ink outline-none placeholder:text-cool-ink-4 focus:border-steel/50'
const PRIMARY =
  'w-full rounded-lg bg-steel py-2.5 text-[12.5px] font-medium text-white disabled:cursor-not-allowed disabled:opacity-50'

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

function ErrorBox({ text }: { text: string }) {
  return (
    <div className="mb-3 rounded-lg border border-clay/45 bg-clay/12 px-3 py-2 text-[12.5px] text-clay-deep">{text}</div>
  )
}
