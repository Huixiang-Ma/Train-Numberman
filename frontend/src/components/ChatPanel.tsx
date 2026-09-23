import { useCallback, useRef, useState } from 'react'
import { api, type DialogResult } from '../api/client'

interface Message {
  role: 'user' | 'bot'
  text: string
  citations?: string[]
  intent?: string
}

interface Props {
  sessionId: string | null
  onResult: (result: DialogResult) => void
  disabled?: boolean
}

/** 工单18 · 对话面板：多模态提问 → 后端 LangGraph 调度 → 回答 + 数字人驱动 */
export default function ChatPanel({ sessionId, onResult, disabled }: Props) {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'bot',
      text: '你好，我是文旅数字人。可以拍照识物、语音提问，也可以让我为你规划路线；对着摄像头挥手，我会主动打招呼。',
    },
  ])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const pushMessage = useCallback((message: Message) => {
    setMessages((previous) => [...previous, message])
  }, [])

  const send = useCallback(
    async (text: string, image?: File) => {
      if (busy || (!text.trim() && !image)) return
      setBusy(true)
      pushMessage({ role: 'user', text: text.trim() || '（上传照片）' })
      try {
        const form = new FormData()
        form.append('text', text.trim() || '请讲解这张图片')
        if (sessionId) form.append('session_id', sessionId)
        form.append('with_avatar', 'true')
        form.append('with_perception', 'true')
        if (image) form.append('image', image)

        const result = await api.dialogMultimodal(form)
        pushMessage({
          role: 'bot',
          text: result.answer_text,
          citations: result.citations.map((item) => item.title),
          intent: result.intent,
        })
        onResult(result)
      } catch (error) {
        pushMessage({ role: 'bot', text: `请求失败：${(error as Error).message}` })
      } finally {
        setBusy(false)
      }
    },
    [busy, onResult, pushMessage, sessionId],
  )

  const onPickImage = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0]
      if (file) void send(input, file)
      event.target.value = ''
      setInput('')
    },
    [input, send],
  )

  return (
    <section className="flex min-h-[420px] flex-col rounded-2xl border border-sand bg-surface p-5 shadow-panel">
      <header className="mb-3 flex items-baseline justify-between gap-3">
        <h2 className="font-display text-base">对话</h2>
        <span className="text-[11.5px] text-ink-4">{sessionId ? `会话 ${sessionId.slice(0, 8)}` : '会话未建立'}</span>
      </header>

      <div className="flex max-h-[46vh] flex-1 flex-col gap-3 overflow-y-auto pr-1">
        {messages.map((message, index) => (
          <div
            key={index}
            className={`flex max-w-[94%] gap-2.5 ${message.role === 'user' ? 'ml-auto flex-row-reverse' : ''}`}
          >
            <div
              className={`grid h-7 w-7 flex-none place-items-center rounded-lg font-display text-[12px] ${
                message.role === 'user'
                  ? 'border border-sand bg-surface-2 text-ink-2'
                  : 'bg-gradient-to-br from-amber-soft to-amber-deep text-[#FFF8EC]'
              }`}
            >
              {message.role === 'user' ? '我' : '智'}
            </div>
            <div
              className={`min-w-0 rounded-xl border px-3.5 py-2.5 text-[13.5px] leading-relaxed ${
                message.role === 'user'
                  ? 'border-amber bg-amber text-[#FFF8EC]'
                  : 'border-sand bg-surface-2 text-ink'
              }`}
              style={{ overflowWrap: 'anywhere' }}
            >
              {message.text}
              {message.citations && message.citations.length > 0 && (
                <>
                  <span className="mt-2 block border-t border-dashed border-sand pt-2 text-[11px] text-ink-3">
                    来源：景区权威知识库
                  </span>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {message.citations.map((title) => (
                      <span
                        key={title}
                        className="rounded-full border border-sand bg-surface px-2.5 py-0.5 text-[11px] text-ink-2"
                      >
                        {title}
                      </span>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>
        ))}
      </div>

      <form
        className="mt-3 flex items-center gap-2 rounded-full border border-sand bg-surface-2 p-1.5 pl-3 focus-within:border-amber"
        onSubmit={(event) => {
          event.preventDefault()
          void send(input)
          setInput('')
        }}
      >
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          title="拍照识别"
          className="grid h-8 w-8 flex-none place-items-center rounded-full text-ink-3 transition hover:bg-surface hover:text-amber"
        >
          📷
        </button>
        <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={onPickImage} />
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="试着问：主殿的木构有什么特点？"
          className="min-w-0 flex-1 bg-transparent px-1 py-1.5 text-[14px] outline-none placeholder:text-ink-4"
        />
        <button
          type="submit"
          disabled={busy || disabled}
          className="rounded-full bg-amber px-4 py-2 text-[13px] text-[#FFF8EC] transition hover:bg-amber-deep disabled:opacity-50"
        >
          {busy ? '生成中…' : '发送'}
        </button>
      </form>
    </section>
  )
}
