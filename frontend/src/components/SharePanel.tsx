import { useCallback, useEffect, useState } from 'react'
import { api, type CreationAsset, type ShareResult, type ShareView } from '../api/client'

/** 工单19 · 多模态内容输出与分享（对应 /create/assets、/share） */

const KIND_LABEL: Record<string, string> = {
  artistic: '艺术化纪念照',
  postcard: '明信片',
  group_photo: '虚拟合影',
  video: '旅行短片',
  diary: '旅行日记',
  guide: '活动攻略',
}

export default function SharePanel() {
  const [items, setItems] = useState<CreationAsset[]>([])
  const [total, setTotal] = useState(0)
  const [shares, setShares] = useState<Record<string, ShareResult>>({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [preview, setPreview] = useState<CreationAsset | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.createAssets()
      setItems(data.items)
      setTotal(data.total)
    } catch (exception) {
      setError((exception as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const share = async (asset: CreationAsset) => {
    try {
      const result = await api.share({
        asset_id: asset.id,
        channel: 'poster',
        title: asset.title,
        summary: asset.text_content ? asset.text_content.slice(0, 120) : '来自文旅创新智脑的旅行纪念',
      })
      setShares((previous) => ({ ...previous, [asset.id]: result }))
    } catch (exception) {
      setError((exception as Error).message)
    }
  }

  return (
    <section className="rounded-2xl border border-sand bg-surface p-5 shadow-panel">
      <header className="mb-3 flex items-baseline justify-between gap-3">
        <h2 className="font-display text-base">我的创作与分享</h2>
        <span className="text-[11.5px] text-ink-4">共 {total} 件 · 可下载 / 分享</span>
      </header>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="rounded-full bg-amber px-4 py-2 text-[13px] text-[#FFF8EC] transition hover:bg-amber-deep disabled:opacity-50"
        >
          {loading ? '加载中…' : '刷新列表'}
        </button>
      </div>

      {error && (
        <div className="mt-3 rounded-xl border border-clay/40 bg-clay/10 px-4 py-2.5 text-[12.5px] text-clay">{error}</div>
      )}

      {items.length === 0 && !loading && (
        <div className="mt-3 rounded-xl border border-sand bg-surface-2 px-4 py-3 text-[12.5px] text-ink-3">
          还没有生成内容。到「纪念内容」生成一张明信片或一段短片，就会出现在这里。
        </div>
      )}

      <ul className="mt-3 flex flex-col gap-2">
        {items.map((asset) => {
          const isVideo = asset.mime?.startsWith('video')
          const isText = asset.kind === 'diary'
          const shareInfo = shares[asset.id]
          return (
            <li key={asset.id} className="rounded-xl border border-sand bg-surface-2 px-3.5 py-2.5">
              <div className="flex flex-wrap items-baseline gap-2">
                <span className="rounded-full border border-sand bg-surface px-2 py-0.5 text-[11px] text-ink-3">
                  {KIND_LABEL[asset.kind] ?? asset.kind}
                </span>
                <span className="text-[13px] text-ink">{asset.title}</span>
                <span className="text-[11px] text-ink-4">{(asset.size_bytes / 1024).toFixed(0)} KB</span>
              </div>

              <div className="mt-2 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => setPreview(preview?.id === asset.id ? null : asset)}
                  className="rounded-full border border-sand bg-surface px-3 py-1 text-[12px] text-ink-2 transition hover:border-amber hover:text-amber"
                >
                  {preview?.id === asset.id ? '收起预览' : '预览'}
                </button>
                {asset.url && (
                  <a
                    href={asset.url}
                    download
                    className="rounded-full border border-sand bg-surface px-3 py-1 text-[12px] text-ink-2 transition hover:border-amber hover:text-amber"
                  >
                    下载
                  </a>
                )}
                <button
                  type="button"
                  onClick={() => void share(asset)}
                  className="rounded-full border border-sand bg-surface px-3 py-1 text-[12px] text-ink-2 transition hover:border-amber hover:text-amber"
                >
                  生成分享链接
                </button>
              </div>

              {preview?.id === asset.id && (
                <div className="mt-2">
                  {isText ? (
                    <pre className="whitespace-pre-wrap text-[12px] leading-relaxed text-ink-2">{asset.text_content}</pre>
                  ) : isVideo ? (
                    <video src={asset.url ?? ''} controls className="w-full rounded-lg border border-sand" />
                  ) : (
                    asset.url && <img src={asset.url} alt={asset.title} className="w-full rounded-lg border border-sand" />
                  )}
                </div>
              )}

              {shareInfo && (
                <div className="mt-2 rounded-lg border border-amber/30 bg-amber-soft/20 px-3 py-2 text-[12px] text-amber-deep">
                  <div className="break-all">分享链接：{shareInfo.url}</div>
                  {shareInfo.poster_url && (
                    <img src={shareInfo.poster_url} alt="分享海报" className="mt-2 w-36 rounded-lg border border-sand" />
                  )}
                </div>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}

/**
 * 分享落地页：读取 ?share=<token> 后渲染被分享的内容。
 *
 * 用查询参数而非路径段：前端是单页应用且未引入路由库，查询参数由 URLSearchParams
 * 直接读取，刷新与直达都不依赖服务端 rewrite。
 */
export function SharedContentView({ token, onExit }: { token: string; onExit: () => void }) {
  const [view, setView] = useState<ShareView | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .shareView(token)
      .then(setView)
      .catch((exception) => setError((exception as Error).message))
  }, [token])

  const asset = view?.asset
  const isVideo = asset?.mime?.startsWith('video')

  return (
    <section className="mx-auto w-full max-w-3xl rounded-2xl border border-sand bg-surface p-6 shadow-panel">
      <header className="mb-4 flex items-baseline justify-between gap-3">
        <h2 className="font-display text-lg">分享内容</h2>
        <button
          type="button"
          onClick={onExit}
          className="rounded-full border border-sand bg-surface px-3 py-1 text-[12px] text-ink-2 transition hover:border-amber hover:text-amber"
        >
          返回导览
        </button>
      </header>

      {error && (
        <div className="rounded-xl border border-clay/40 bg-clay/10 px-4 py-3 text-[13px] text-clay">{error}</div>
      )}

      {view && (
        <div>
          <div className="font-display text-[17px] text-ink">{view.title}</div>
          <div className="mt-1 text-[13px] leading-relaxed text-ink-3">{view.summary}</div>
          <div className="mt-1 text-[11.5px] text-ink-4">
            {view.channel} · 访问 {view.visits} 次
          </div>

          <div className="mt-4">
            {!asset && view.poster_url && (
              <img src={view.poster_url} alt="分享海报" className="w-full rounded-xl border border-sand" />
            )}
            {asset?.kind === 'diary' && (
              <pre className="whitespace-pre-wrap rounded-xl border border-sand bg-surface-2 p-4 text-[13px] leading-relaxed text-ink-2">
                {asset.text_content}
              </pre>
            )}
            {asset && asset.kind !== 'diary' && isVideo && (
              <video src={asset.url ?? ''} controls className="w-full rounded-xl border border-sand" />
            )}
            {asset && asset.kind !== 'diary' && !isVideo && asset.url && (
              <img src={asset.url} alt={asset.title} className="w-full rounded-xl border border-sand" />
            )}
          </div>

          {asset?.url && (
            <a
              href={asset.url}
              download
              className="mt-3 inline-block rounded-full bg-amber px-4 py-2 text-[13px] text-[#FFF8EC] transition hover:bg-amber-deep"
            >
              下载原件
            </a>
          )}
        </div>
      )}
    </section>
  )
}
