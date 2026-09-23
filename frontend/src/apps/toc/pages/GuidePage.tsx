/**
 * 工单18 · 智能导览与互动体验（由原 App.tsx 迁移）
 * 工单16-20 延伸 · 平台化双端重构（批次 0）：迁入 ToC 路由 /guide，
 * 外层 chrome（顶栏 / 底部 Tab / 页脚）交由 TocShell 统一提供。
 *
 * 数字人全身视觉交互（本轮）：
 *   · 视觉识别不再单独成面板 —— 结果由数字人本体表达（动作/表情/语音/口型）；
 *   · 字幕气泡、摄像头与上传入口收进舞台（AvatarInteractionOverlay）；
 *   · 自动讲解按事件 key 去重，并在数字人播报期间挂起，避免打断正在说的话。
 *
 * AvatarStage.tsx 的骨骼/口型/动作驱动保持不变（约束 H1）。
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  api,
  playDrive,
  type AvatarDrive,
  type AvatarInteraction,
  type AvatarProfile,
  type DialogResult,
} from '../../../api/client'
import AvatarInteractionOverlay from '../../../components/AvatarInteractionOverlay'
import AvatarStage, { type AvatarVisualState } from '../../../components/AvatarStage'
import ChatPanel from '../../../components/ChatPanel'
import { useAvatarAssets } from '../../../hooks/useAvatarAssets'
import { usePerceptionSocket } from '../../../hooks/usePerceptionSocket'
import { interactionKey, shouldSpeakInteraction } from '../../../shared/utils/avatarInteraction'

const IDLE_STATE: AvatarVisualState = { emotion: 'calm', motion: 'idle', speaking: false, mouth: 0 }

const MOTION_LABEL: Record<string, string> = {
  idle: '待机',
  wave: '挥手',
  greet: '问候',
  nod: '点头',
  shake: '摇头',
  point: '指向',
  explain: '讲解',
}

const EMOTION_LABEL: Record<string, string> = {
  calm: '平和',
  cheerful: '愉快',
  curious: '好奇',
  gentle: '温和',
}

export default function GuidePage() {
  const socket = usePerceptionSocket(true)
  // 全身立绘（qingci-full）：数字人需要完整形体来表现动作与衣摆；
  // 半身像 qingci 仍保留在资产目录，切换 id 即可回退。
  const avatarAssets = useAvatarAssets('qingci-full')

  const [visual, setVisual] = useState<AvatarVisualState>(IDLE_STATE)
  const [profile, setProfile] = useState<AvatarProfile | null>(null)
  const [stackInfo, setStackInfo] = useState<Record<string, unknown> | null>(null)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const stopRef = useRef<(() => void) | null>(null)
  const resetTimer = useRef<number | null>(null)
  // 口型开合度与当前视位逐帧变化，走 ref 直连 3D 循环，避免 60fps 触发 React 重渲染
  const mouthRef = useRef(0)
  const visemeRef = useRef<string | null>(null)
  // 播报编排：已播事件的 key、待播事件、当前是否在播报
  const spokenKeyRef = useRef<string | null>(null)
  const pendingRef = useRef<AvatarInteraction | null>(null)
  const speakingRef = useRef(false)

  /** 播放一段数字人语音并驱动唇形/表情/动作；结束后回调，用于接续挂起的讲解 */
  const applyDrive = useCallback((drive: AvatarDrive, onDone?: () => void) => {
    stopRef.current?.()
    if (resetTimer.current) window.clearTimeout(resetTimer.current)

    mouthRef.current = 0
    visemeRef.current = null
    speakingRef.current = true
    setVisual({ emotion: drive.emotion, motion: drive.motion, speaking: true, mouth: 0 })
    stopRef.current = playDrive(drive, (viseme, open) => {
      mouthRef.current = open
      visemeRef.current = viseme
    })
    resetTimer.current = window.setTimeout(
      () => {
        speakingRef.current = false
        setVisual((previous) => ({ ...previous, speaking: false, mouth: 0, motion: 'idle' }))
        onDone?.()
      },
      drive.duration_ms + 500,
    )
  }, [])

  const speakRef = useRef<(event: AvatarInteraction) => void>(() => undefined)

  /** 播报一条交互事件；驱动缺失（TTS/驱动降级）时只保留字幕，不做动作 */
  const speak = useCallback(
    (event: AvatarInteraction) => {
      spokenKeyRef.current = interactionKey(event)
      if (!event.drive) return
      applyDrive(event.drive, () => {
        // 播报期间到达的新事件此时才播：既不错过，也不打断当前这句话
        const pending = pendingRef.current
        pendingRef.current = null
        if (pending && interactionKey(pending) !== spokenKeyRef.current) speakRef.current(pending)
      })
    },
    [applyDrive],
  )

  useEffect(() => {
    speakRef.current = speak
  }, [speak])

  useEffect(() => {
    api
      .avatarProfile()
      .then(setProfile)
      .catch(() => setError('后端未就绪，请先启动 uvicorn（127.0.0.1:8100）'))
    api.stack().then(setStackInfo).catch(() => undefined)
    return () => {
      stopRef.current?.()
      if (resetTimer.current) window.clearTimeout(resetTimer.current)
    }
  }, [])

  /** 消费统一交互事件：去重 → 播报或挂起 → 清空，避免同一目标反复触发 */
  useEffect(() => {
    const event = socket.interaction
    if (!event) return
    const key = interactionKey(event)
    if (key === spokenKeyRef.current) {
      socket.clearInteraction()
      return
    }
    if (!shouldSpeakInteraction(event)) return
    if (speakingRef.current) {
      pendingRef.current = event
      return
    }
    speak(event)
    socket.clearInteraction()
  }, [socket.interaction, socket.clearInteraction, speak])

  const handleResult = useCallback(
    (result: DialogResult) => {
      setSessionId(result.session_id)
      if (result.avatar) applyDrive(result.avatar)
    },
    [applyDrive],
  )

  const chips = [
    stackInfo?.llm && `LLM ${String(stackInfo.llm)}`,
    stackInfo?.embedding_model && `向量 ${String(stackInfo.embedding_model)}`,
    stackInfo?.reranker && `重排 ${String(stackInfo.reranker)}`,
    stackInfo?.asr && `ASR ${String(stackInfo.asr)}`,
  ].filter(Boolean) as string[]

  return (
    <div className="flex flex-col gap-4">
      {error && (
        <div className="rounded-xl border border-clay/40 bg-clay/10 px-4 py-2.5 text-[13px] text-clay">
          {error}
        </div>
      )}

      {/* 技术栈信息原先在页头；页头改由 TocShell 提供后移到这里，避免能力展示丢失 */}
      {chips.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {chips.map((chip) => (
            <span
              key={chip}
              className="max-w-[280px] truncate rounded-full border border-sand bg-surface px-3 py-1 text-[11px] text-ink-3"
            >
              {chip}
            </span>
          ))}
        </div>
      )}

      {/*
        问答页入口。docs/09 §4.3 的底部 Tab 定为「发现/导览/行程/票务/我的」，
        问答不再占格，因此必须在这里给出入链 —— 否则 /ask 会成为无法抵达的死页。
      */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-sand bg-surface/70 px-4 py-3 shadow-panel">
        <p className="text-[12.5px] leading-relaxed text-ink-3">
          想直接问问题？问答页支持文字、语音与拍照提问，回答会附知识库出处。
        </p>
        <Link
          to="/ask"
          className="shrink-0 rounded-xl border border-sand bg-surface px-3.5 py-2 text-[12.5px] text-ink-2"
        >
          去多模态问答
        </Link>
      </div>

      <main className="grid grid-cols-1 gap-4 sm:gap-5 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <div className="flex flex-col gap-4">
          {/* 舞台 + 交互层：识别反馈、字幕与采集控件都在人物这一侧，不再另开面板 */}
          <div className="relative overflow-hidden rounded-3xl border border-sand bg-gradient-to-b from-surface/70 to-surface/30 pb-[188px]">
            <AvatarStage state={visual} assets={avatarAssets} mouthRef={mouthRef} visemeRef={visemeRef} />
            <AvatarInteractionOverlay
              interaction={socket.interaction}
              socket={socket}
              speaking={visual.speaking}
            />
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="font-display text-lg text-ink">{profile?.name ?? '青瓷'}</div>
              {/* 说话声波：舞台外的状态反馈 */}
              <div className="flex h-5 items-end gap-[3px]" aria-hidden>
                {Array.from({ length: 22 }).map((_, index) => (
                  <span
                    key={index}
                    className={`w-[3px] rounded-full ${visual.speaking ? 'wave-bar' : 'wave-bar wave-bar--idle'}`}
                    style={{
                      animationDelay: `${(index % 11) * 48}ms`,
                      background: 'linear-gradient(180deg,#e8c06a,#b4532f)',
                    }}
                  />
                ))}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <span className="rounded-full border border-sand bg-surface px-3 py-1 text-[11.5px] text-ink-2">
                情绪 · {EMOTION_LABEL[visual.emotion] ?? visual.emotion}
              </span>
              <span className="rounded-full border border-sand bg-surface px-3 py-1 text-[11.5px] text-ink-2">
                动作 · {MOTION_LABEL[visual.motion] ?? visual.motion}
              </span>
              <span
                className={`rounded-full border px-3 py-1 text-[11.5px] ${
                  visual.speaking ? 'border-clay bg-clay/12 text-clay' : 'border-sand bg-surface text-ink-3'
                }`}
              >
                唇形 · {visual.speaking ? '播报中' : '静默'}
              </span>
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-5">
          <ChatPanel sessionId={sessionId} onResult={handleResult} />
        </div>
      </main>

      {/* 技术栈总表：工单验收需要展示，故保留（页头改由 TocShell 承载后不随之丢失） */}
      <footer className="pt-2 text-[11.5px] leading-relaxed text-ink-4">
        技术栈：FastAPI + LangGraph + Milvus + BGE-M3 + Chinese-CLIP + bge-reranker-v2 + Qwen + PaddleOCR + FunASR + CosyVoice + YOLO11 + SAM 2 + MediaPipe + 通义万相 Qwen-Image + FFmpeg + OpenCV + Mermaid
      </footer>
    </div>
  )
}
