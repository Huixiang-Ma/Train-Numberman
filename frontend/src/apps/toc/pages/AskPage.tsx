/**
 * 工单17 §1 · ToC 多模态知识问答（S1）
 * 工单18 §1 要求「支持语音、文本、图片、视频等多模态输入与输出」。
 *
 * 与 /guide 的职责区分：
 *   /guide  数字人为主角（形象 + 实时感知），问答是"和数字人说话"
 *   /ask    结果为主角（答案 + 引用来源 + 识别结果），适合阅读与核对
 * 两者共用同一套后端对话能力与会话上下文。
 *
 * 本页补齐了此前缺失的语音输入入口（后端一直支持 audio，前端从未实现录音）。
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, playDrive, type DialogResult } from '../../../api/client'
import StateView from '../../../shared/components/StateView'
import { useAsync } from '../../../shared/hooks/useAsync'
import { useAudioRecorder } from '../hooks/useAudioRecorder'

type Turn = { id: string; question: string; imageUrl: string | null; voice: string | null; result: DialogResult }

const INTENT_LABEL: Record<string, string> = {
  知识: '知识问答',
  规划: '行程规划',
  活动: '活动推荐',
  创作: '内容创作',
  闲聊: '闲聊',
}

export default function AskPage() {
  const [turns, setTurns] = useState<Turn[]>([])
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [text, setText] = useState('')
  const [image, setImage] = useState<{ file: File; url: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [speakingId, setSpeakingId] = useState<string | null>(null)

  const recorder = useAudioRecorder()
  const fileRef = useRef<HTMLInputElement>(null)
  const stopSpeakRef = useRef<(() => void) | null>(null)

  // 预览图是 object URL，必须显式释放，否则每传一张图就泄漏一份内存
  useEffect(() => () => { if (image) URL.revokeObjectURL(image.url) }, [image])
  useEffect(() => () => stopSpeakRef.current?.(), [])

  const pickImage = (file: File | null) => {
    if (image) URL.revokeObjectURL(image.url)
    setImage(file ? { file, url: URL.createObjectURL(file) } : null)
  }

  const submit = useCallback(
    async (payload: { text: string; image?: File; audio?: { blob: Blob; mime: string } }) => {
      setBusy(true)
      setError(null)
      try {
        let result: DialogResult
        if (payload.image || payload.audio) {
          const form = new FormData()
          if (sessionId) form.append('session_id', sessionId)
          if (payload.text) form.append('text', payload.text)
          form.append('lang', 'zh')
          form.append('with_avatar', 'true')
          form.append('with_perception', 'true')
          if (payload.image) form.append('image', payload.image)
          if (payload.audio) {
            // 文件名要与 mime 对应：后端按 audio/wav 之类的声明解析，名字不对会误判格式
            const ext = payload.audio.mime.includes('webm') ? 'webm' : payload.audio.mime.includes('wav') ? 'wav' : 'ogg'
            form.append('audio', payload.audio.blob, `voice.${ext}`)
          }
          result = await api.dialogMultimodal(form)
        } else {
          result = await api.dialog({ session_id: sessionId ?? undefined, text: payload.text, with_avatar: true })
        }

        setSessionId(result.session_id)
        const objectUrl = payload.image ? URL.createObjectURL(payload.image) : null
        setTurns((previous) => [
          ...previous,
          {
            id: result.session_id + String(previous.length),
            question: result.question || payload.text || (payload.audio ? '（语音提问）' : '（图片提问）'),
            imageUrl: objectUrl,
            voice: result.asr_text,
            result,
          },
        ])
        setText('')
        setImage(null)
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : String(caught))
      } finally {
        setBusy(false)
      }
    },
    [sessionId],
  )

  /** 朗读某条答案：只播音频、不驱动 3D 舞台（本页没有舞台） */
  const speak = useCallback(
    async (turnId: string, content: string) => {
      stopSpeakRef.current?.()
      stopSpeakRef.current = null
      if (speakingId === turnId) {
        setSpeakingId(null)
        return
      }
      setSpeakingId(turnId)
      try {
        const drive = await api.drive(content)
        stopSpeakRef.current = playDrive(drive, (viseme) => {
          // playDrive 在结束或停止时会回调 (null, 0)，据此复位按钮
          if (viseme === null) setSpeakingId(null)
        })
      } catch (caught) {
        setSpeakingId(null)
        setError(`语音合成失败：${caught instanceof Error ? caught.message : String(caught)}`)
      }
    },
    [speakingId],
  )

  const stack = useAsync(() => api.stack(), 'stack')

  return (
    <div className="flex flex-col gap-4">
      <section className="rounded-2xl border border-sand bg-surface/70 px-5 py-4 shadow-panel">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="font-display text-[21px] leading-tight text-ink">多模态问答</h1>
            <p className="mt-1 text-[12.5px] text-ink-3">
              用文字、拍照或语音提问；答案会附上知识来源，便于核对。
            </p>
          </div>
          {turns.length > 0 && (
            <button
              onClick={() => {
                stopSpeakRef.current?.()
                setSpeakingId(null)
                setTurns([])
                setSessionId(null)
              }}
              className="rounded-lg border border-sand bg-surface px-3 py-1.5 text-[12.5px] text-ink-3"
            >
              开始新会话
            </button>
          )}
        </div>
        {stack.state.kind === 'ready' && (
          <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-ink-4">
            {['llm', 'embedding_model', 'reranker'].map((key) =>
              stack.state.kind === 'ready' && stack.state.data[key] ? (
                <span key={key} className="rounded-full border border-sand bg-surface-2 px-2 py-0.5">
                  {String(stack.state.data[key])}
                </span>
              ) : null,
            )}
          </div>
        )}
      </section>

      {/* 输入区 */}
      <section className="rounded-2xl border border-sand bg-surface px-4 py-4">
        <form
          onSubmit={(event) => {
            event.preventDefault()
            const trimmed = text.trim()
            if (!trimmed && !image && recorder.state !== 'recording') return
            void submit({ text: trimmed, image: image?.file })
          }}
        >
          <textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            rows={3}
            placeholder="例如：主殿的木构有什么特点？／这里有哪些必打卡的景点？"
            className="w-full resize-none rounded-xl border border-sand bg-surface px-3.5 py-2.5 text-[13.5px] leading-relaxed text-ink outline-none placeholder:text-ink-4 focus:border-amber/50"
          />

          {image && (
            <div className="mt-2 flex items-center gap-3 rounded-xl border border-sand bg-surface-2/60 px-3 py-2">
              <img src={image.url} alt="待提问的图片" className="h-14 w-14 rounded-lg object-cover" />
              <span className="min-w-0 flex-1 truncate text-[12px] text-ink-2">{image.file.name}</span>
              <button type="button" onClick={() => pickImage(null)} className="text-[12px] text-clay">
                移除
              </button>
            </div>
          )}

          {recorder.error && (
            <div className="mt-2 rounded-xl border border-clay/40 bg-clay/10 px-3 py-2 text-[12px] text-clay-deep">
              {recorder.error}
            </div>
          )}

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(event) => pickImage(event.target.files?.[0] ?? null)}
            />
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              className="rounded-xl border border-sand bg-surface px-3 py-2 text-[12.5px] text-ink-2 hover:border-amber/45"
            >
              拍照 / 传图
            </button>

            {recorder.state === 'unsupported' ? (
              <span className="rounded-xl border border-dashed border-sand px-3 py-2 text-[12px] text-ink-4">
                当前浏览器不支持录音，请改用文字或图片提问
              </span>
            ) : recorder.state === 'recording' ? (
              <button
                type="button"
                onClick={async () => {
                  const recording = await recorder.stop()
                  if (recording) await submit({ text: text.trim(), audio: { blob: recording.blob, mime: recording.mime } })
                }}
                className="rounded-xl bg-clay px-3 py-2 text-[12.5px] text-white"
              >
                结束并提问 · {recorder.seconds}s
              </button>
            ) : (
              <button
                type="button"
                onClick={() => void recorder.start()}
                disabled={recorder.state === 'requesting'}
                className="rounded-xl border border-sand bg-surface px-3 py-2 text-[12.5px] text-ink-2 hover:border-amber/45 disabled:opacity-50"
              >
                {recorder.state === 'denied' ? '麦克风被拒绝' : recorder.state === 'requesting' ? '请求麦克风…' : '语音提问'}
              </button>
            )}

            <button
              type="submit"
              disabled={busy || (!text.trim() && !image)}
              className="ml-auto rounded-xl bg-gradient-to-br from-amber-soft to-amber-deep px-4 py-2 text-[13px] text-[#FFF8EC] disabled:opacity-50"
            >
              {busy ? '检索中…' : '提问'}
            </button>
          </div>
        </form>
      </section>

      {error && <div className="rounded-xl border border-clay/40 bg-clay/10 px-4 py-2.5 text-[13px] text-clay-deep">{error}</div>}

      {/* 结果 */}
      {turns.length === 0 ? (
        <StateView state={stack.state} tone="warm" loadingText="正在准备问答（检查后端）…">
          {() => (
            <div className="rounded-2xl border border-dashed border-sand bg-surface/70 px-6 py-10 text-center">
              <div className="font-display text-[16px] text-ink">还没有提问</div>
              <p className="mx-auto mt-1 max-w-[520px] text-[12.5px] leading-relaxed text-ink-3">
                可以试试：「主殿的木构有什么特点」「东壁壁画画的是什么故事」，
                或直接拍一张碑刻/建筑照片上传。
              </p>
              <div className="mt-4 flex justify-center gap-2">
                <Link to="/guide" className="rounded-xl border border-sand bg-surface px-3.5 py-2 text-[12.5px] text-ink-2">
                  去数字人导览
                </Link>
                <Link to="/explore" className="rounded-xl border border-sand bg-surface px-3.5 py-2 text-[12.5px] text-ink-2">
                  先浏览景区
                </Link>
              </div>
            </div>
          )}
        </StateView>
      ) : (
        <div className="flex flex-col gap-4">
          {turns.map((turn) => (
            <article key={turn.id} className="rounded-2xl border border-sand bg-surface px-4 py-4 shadow-panel sm:px-5">
              {/* 提问 */}
              <div className="flex gap-3">
                {turn.imageUrl && <img src={turn.imageUrl} alt="提问图片" className="h-16 w-16 shrink-0 rounded-lg object-cover" />}
                <div className="min-w-0 flex-1">
                  <div className="text-[13.5px] font-medium text-ink">{turn.question}</div>
                  {turn.voice && (
                    <div className="mt-0.5 text-[11.5px] text-ink-3">语音识别：{turn.voice}</div>
                  )}
                  <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[11px]">
                    <span className="rounded-full bg-amber/12 px-2 py-0.5 text-amber-deep">
                      {INTENT_LABEL[turn.result.intent] ?? turn.result.intent}
                    </span>
                    {turn.result.workflow && (
                      <span className="rounded-full border border-sand bg-surface-2 px-2 py-0.5 text-ink-3">
                        {turn.result.workflow}
                      </span>
                    )}
                    {turn.result.session_turns > 1 && (
                      <span className="text-ink-4">第 {turn.result.session_turns} 轮</span>
                    )}
                  </div>
                </div>
              </div>

              {/* 答案 */}
              <p className="mt-3 whitespace-pre-wrap text-[13.5px] leading-relaxed text-ink-2">{turn.result.answer_text}</p>

              {turn.result.ocr_text && (
                <div className="mt-2.5 rounded-xl border border-sand bg-surface-2/60 px-3 py-2 text-[12px] text-ink-3">
                  <span className="text-ink-4">OCR 识别：</span>
                  {turn.result.ocr_text}
                </div>
              )}

              {/* 媒体 */}
              {turn.result.medias.length > 0 && (
                <div className="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-4">
                  {turn.result.medias.map((item) => (
                    <img
                      key={item.url}
                      src={item.url}
                      alt="相关知识图片"
                      className="h-24 w-full rounded-lg border border-sand object-cover"
                    />
                  ))}
                </div>
              )}

              {/* 引用来源 */}
              {turn.result.citations.length > 0 && (
                <div className="mt-3 rounded-xl border border-sand bg-surface-2/50 px-3.5 py-2.5">
                  <div className="mb-1.5 text-[11.5px] text-ink-4">知识来源（{turn.result.citations.length}）</div>
                  <ul className="flex flex-col gap-1.5">
                    {turn.result.citations.map((item) => (
                      <li key={item.kb_id} className="flex flex-wrap items-baseline gap-x-2 text-[12px]">
                        <span className="text-ink-2">{item.title}</span>
                        {item.source && <span className="text-ink-4">{item.source}</span>}
                        <span className="text-ink-4">相关度 {item.score.toFixed(2)}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="mt-3 flex flex-wrap items-center gap-2">
                <button
                  onClick={() => void speak(turn.id, turn.result.answer_text)}
                  className={`rounded-lg border px-3 py-1.5 text-[12.5px] ${
                    speakingId === turn.id ? 'border-clay bg-clay/12 text-clay-deep' : 'border-sand bg-surface text-ink-2'
                  }`}
                >
                  {speakingId === turn.id ? '停止朗读' : '朗读答案'}
                </button>
                {turn.result.avatar?.degraded && (
                  <span className="text-[11.5px] text-clay">语音合成不可用（{turn.result.avatar.degraded}），已降级为文字</span>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  )
}
