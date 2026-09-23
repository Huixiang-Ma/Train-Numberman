import { useRef, useState } from 'react'
import {
  api,
  pollCreationTask,
  type CreationAsset,
  type CreationTask,
  type ShareResult,
} from '../api/client'

/** 工单19 · 专属纪念内容自动生成（对应 /create/image、/create/video、/create/diary） */

type Mode = 'artistic' | 'postcard' | 'group_photo' | 'video' | 'diary'

const MODES: { key: Mode; label: string; hint: string }[] = [
  { key: 'artistic', label: '艺术化纪念照', hint: '保留本人相貌，只换画风' },
  { key: 'postcard', label: '明信片', hint: '风格化 + 可邮寄版式' },
  { key: 'group_photo', label: '虚拟合影', hint: 'AI 场景 + 人像合成' },
  { key: 'video', label: '旅行短片', hint: '运镜 + 转场 + 字幕' },
  { key: 'diary', label: '旅行日记', hint: '按行程要素成文' },
]

const STYLES = [
  { key: 'ink', label: '水墨写意' },
  { key: 'gongbi', label: '工笔重彩' },
  { key: 'oil', label: '古典油画' },
  { key: 'film', label: '复古胶片' },
  { key: 'anime', label: '新海诚动画' },
  { key: 'tang', label: '唐风重彩' },
]

const TONES = ['温暖记录', '文艺随笔', '轻松活泼']

export default function CreationPanel() {
  const [mode, setMode] = useState<Mode>('postcard')
  const [style, setStyle] = useState('ink')
  const [title, setTitle] = useState('')
  const [place, setPlace] = useState('')
  const [note, setNote] = useState('')
  const [scene, setScene] = useState('中国古典园林中的庭院，飞檐回廊，暖阳斜照')
  const [captions, setCaptions] = useState('')
  const [tone, setTone] = useState('温暖记录')
  const [withNarration, setWithNarration] = useState(false)
  const [files, setFiles] = useState<File[]>([])
  const [asset, setAsset] = useState<CreationAsset | null>(null)
  const [share, setShare] = useState<ShareResult | null>(null)
  const [progress, setProgress] = useState<{ value: number; message: string } | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const needsPhotos = mode !== 'diary'

  const reset = () => {
    setAsset(null)
    setShare(null)
    setProgress(null)
    setError(null)
  }

  const pick = (selected: FileList | null) => {
    if (!selected) return
    setFiles(Array.from(selected).slice(0, 12))
  }

  /** 异步任务轮询：后端返回 task_id 时持续查询直到出结果 */
  const awaitTask = async (result: CreationAsset | CreationTask) => {
    if ('asset' in result) {
      const finished: CreationTask = await pollCreationTask(result.task_id, (task) =>
        setProgress({ value: task.progress, message: task.message }),
      )
      if (finished.status === 'failed') throw new Error(finished.error || '生成失败')
      if (!finished.asset) throw new Error('任务已完成但未返回产物')
      return finished.asset
    }
    return result
  }

  const generate = async () => {
    setLoading(true)
    reset()
    try {
      let produced: CreationAsset
      if (mode === 'diary') {
        produced = await api.createDiary({
          title: title || '我的旅行日记',
          tone,
          place,
          highlights: captions.split(/[|\n]/).map((item) => item.trim()).filter(Boolean),
        })
      } else {
        if (files.length === 0) throw new Error('请先选择至少一张照片')
        const form = new FormData()
        files.forEach((file) => form.append('files', file))
        form.append('background', 'true')
        if (mode === 'video') {
          form.append('title', title || '我的旅行回忆')
          form.append('captions', captions)
          form.append('with_narration', String(withNarration))
          produced = await awaitTask(await api.createVideo(form))
        } else {
          form.append('kind', mode)
          form.append('style', style)
          form.append('title', title)
          if (mode === 'postcard') {
            form.append('place', place)
            form.append('text', note)
          }
          if (mode === 'group_photo') form.append('scene', scene)
          produced = await awaitTask(await api.createImage(form))
        }
      }
      setAsset(produced)
    } catch (exception) {
      setError((exception as Error).message)
    } finally {
      setLoading(false)
      setProgress(null)
    }
  }

  const shareIt = async () => {
    if (!asset) return
    try {
      setShare(
        await api.share({
          asset_id: asset.id,
          channel: 'poster',
          title: asset.title,
          summary: asset.text_content ? asset.text_content.slice(0, 120) : '来自文旅创新智脑的旅行纪念',
        }),
      )
    } catch (exception) {
      setError((exception as Error).message)
    }
  }

  const isVideo = asset?.mime?.startsWith('video')
  const isText = asset?.kind === 'diary'

  return (
    <section className="rounded-2xl border border-sand bg-surface p-5 shadow-panel">
      <header className="mb-3 flex items-baseline justify-between gap-3">
        <h2 className="font-display text-base">专属纪念内容</h2>
        <span className="text-[11.5px] text-ink-4">照片 → 纪念照 / 明信片 / 合影 / 短片 / 日记</span>
      </header>

      <div className="flex flex-wrap gap-1.5">
        {MODES.map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => {
              setMode(item.key)
              reset()
            }}
            title={item.hint}
            className={`rounded-full border px-3 py-1 text-[12.5px] transition ${
              mode === item.key
                ? 'border-amber bg-amber text-[#FFF8EC]'
                : 'border-sand bg-surface-2 text-ink-2 hover:border-amber hover:text-amber'
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      {needsPhotos && (
        <div className="mt-4">
          <input
            ref={inputRef}
            type="file"
            accept="image/*"
            multiple={mode !== 'artistic' && mode !== 'postcard'}
            onChange={(event) => pick(event.target.files)}
            className="hidden"
          />
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            className="w-full rounded-xl border border-dashed border-sand bg-surface-2 px-4 py-4 text-[13px] text-ink-3 transition hover:border-amber hover:text-amber"
          >
            {files.length > 0 ? `已选择 ${files.length} 张照片（点击可重选）` : '点击选择旅行照片'}
          </button>
          {files.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {files.map((file) => (
                <span key={file.name} className="rounded-lg border border-sand bg-surface px-2 py-1 text-[11px] text-ink-3">
                  {file.name}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {(mode === 'artistic' || mode === 'postcard' || mode === 'group_photo') && (
        <div className="mt-4">
          <div className="mb-1.5 text-[11.5px] text-ink-4">风格</div>
          <div className="flex flex-wrap gap-1.5">
            {STYLES.map((item) => (
              <button
                key={item.key}
                type="button"
                onClick={() => setStyle(item.key)}
                className={`rounded-lg border px-2.5 py-1 text-[12px] transition ${
                  style === item.key
                    ? 'border-amber bg-amber-soft/40 text-amber-deep'
                    : 'border-sand bg-surface-2 text-ink-3 hover:border-amber'
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="mt-4 grid grid-cols-2 gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-[11.5px] text-ink-4">标题</span>
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder={mode === 'diary' ? '我的旅行日记' : '如：西湖纪游'}
            className="rounded-lg border border-sand bg-surface-2 px-3 py-1.5 text-[12.5px] text-ink outline-none focus:border-amber"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[11.5px] text-ink-4">{mode === 'diary' ? '语气' : '地点'}</span>
          {mode === 'diary' ? (
            <select
              value={tone}
              onChange={(event) => setTone(event.target.value)}
              className="rounded-lg border border-sand bg-surface-2 px-3 py-1.5 text-[12.5px] text-ink outline-none focus:border-amber"
            >
              {TONES.map((item) => (
                <option key={item}>{item}</option>
              ))}
            </select>
          ) : (
            <input
              value={place}
              onChange={(event) => setPlace(event.target.value)}
              placeholder="如：杭州西湖"
              className="rounded-lg border border-sand bg-surface-2 px-3 py-1.5 text-[12.5px] text-ink outline-none focus:border-amber"
            />
          )}
        </label>
      </div>

      {mode === 'postcard' && (
        <label className="mt-3 flex flex-col gap-1">
          <span className="text-[11.5px] text-ink-4">题字</span>
          <input
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="如：愿此行有风有月"
            className="rounded-lg border border-sand bg-surface-2 px-3 py-1.5 text-[12.5px] text-ink outline-none focus:border-amber"
          />
        </label>
      )}

      {mode === 'group_photo' && (
        <label className="mt-3 flex flex-col gap-1">
          <span className="text-[11.5px] text-ink-4">合成场景</span>
          <input
            value={scene}
            onChange={(event) => setScene(event.target.value)}
            className="rounded-lg border border-sand bg-surface-2 px-3 py-1.5 text-[12.5px] text-ink outline-none focus:border-amber"
          />
        </label>
      )}

      {(mode === 'video' || mode === 'diary') && (
        <label className="mt-3 flex flex-col gap-1">
          <span className="text-[11.5px] text-ink-4">
            {mode === 'video' ? '每张照片字幕（用 | 分隔）' : '当日亮点（用 | 分隔）'}
          </span>
          <input
            value={captions}
            onChange={(event) => setCaptions(event.target.value)}
            placeholder={mode === 'video' ? '清晨入古寺|曲径通幽处|潭影空人心' : '断桥晨雾|苏堤春晓'}
            className="rounded-lg border border-sand bg-surface-2 px-3 py-1.5 text-[12.5px] text-ink outline-none focus:border-amber"
          />
        </label>
      )}

      {mode === 'video' && (
        <label className="mt-3 flex items-center gap-2 text-[12.5px] text-ink-2">
          <input type="checkbox" checked={withNarration} onChange={(event) => setWithNarration(event.target.checked)} />
          用 CosyVoice 生成解说音轨并混入成片
        </label>
      )}

      <div className="mt-4 flex items-center gap-2">
        <button
          type="button"
          onClick={generate}
          disabled={loading}
          className="rounded-full bg-amber px-4 py-2 text-[13px] text-[#FFF8EC] transition hover:bg-amber-deep disabled:opacity-50"
        >
          {loading ? '生成中…' : '开始生成'}
        </button>
        {asset && (
          <button
            type="button"
            onClick={shareIt}
            className="rounded-full border border-sand bg-surface px-4 py-2 text-[13px] text-ink-2 transition hover:border-amber hover:text-amber"
          >
            生成分享链接
          </button>
        )}
      </div>

      {progress && (
        <div className="mt-3">
          <div className="h-1.5 overflow-hidden rounded-full bg-surface-2">
            <div className="h-full rounded-full bg-amber transition-all" style={{ width: `${progress.value}%` }} />
          </div>
          <div className="mt-1 text-[11.5px] text-ink-4">
            {progress.message || '处理中'}（{progress.value}%）
          </div>
        </div>
      )}

      {error && (
        <div className="mt-3 rounded-xl border border-clay/40 bg-clay/10 px-4 py-2.5 text-[12.5px] text-clay">
          生成失败：{error}
        </div>
      )}

      {asset && (
        <div className="mt-4 animate-rise rounded-xl border border-sand bg-surface-2 p-3.5">
          <div className="font-display text-[14.5px] text-ink">{asset.title}</div>
          <div className="mt-0.5 text-[11.5px] text-ink-4">
            {asset.kind} · {asset.mime} · {(asset.size_bytes / 1024).toFixed(0)} KB · 模型 {asset.model}
          </div>

          {isText ? (
            <pre className="mt-2 whitespace-pre-wrap text-[12.5px] leading-relaxed text-ink-2">{asset.text_content}</pre>
          ) : isVideo ? (
            <video src={asset.url ?? ''} controls className="mt-2 w-full rounded-lg border border-sand" />
          ) : (
            asset.url && <img src={asset.url} alt={asset.title} className="mt-2 w-full rounded-lg border border-sand" />
          )}

          {asset.url && (
            <a
              href={asset.url}
              download
              className="mt-2 inline-block rounded-full border border-sand bg-surface px-3 py-1 text-[12px] text-ink-2 transition hover:border-amber hover:text-amber"
            >
              下载
            </a>
          )}

          {share && (
            <div className="mt-3 rounded-lg border border-amber/30 bg-amber-soft/20 px-3 py-2.5 text-[12px] text-amber-deep">
              <div className="break-all">分享链接：{share.url}</div>
              {share.poster_url && (
                <img src={share.poster_url} alt="分享海报" className="mt-2 w-40 rounded-lg border border-sand" />
              )}
            </div>
          )}
        </div>
      )}
    </section>
  )
}
