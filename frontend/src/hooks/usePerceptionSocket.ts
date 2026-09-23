import { useCallback, useEffect, useRef, useState } from 'react'
import type { AvatarDrive, AvatarInteraction, PerceptionData, Suggestion } from '../api/client'

export interface PerceptionMessage {
  data: PerceptionData
  suggestion: Suggestion | null
  avatar?: { text: string; gesture: string; drive: AvatarDrive }
}

export interface PerceptionSocket {
  status: 'idle' | 'connecting' | 'open' | 'closed'
  providers: Record<string, string>
  latest: PerceptionMessage | null
  greeting: { text: string; drive: AvatarDrive } | null
  /** 服务端已决定的数字人反馈事件（挥手问候 / 稳定目标自动讲解 / 澄清） */
  interaction: AvatarInteraction | null
  connect: () => void
  disconnect: () => void
  configure: (options: { withClassify?: boolean; withSegments?: boolean; withOcr?: boolean }) => void
  sendFrame: (blob: Blob) => void
  clearGreeting: () => void
  clearInteraction: () => void
}

/**
 * 工单18 · 实时感知 WebSocket
 * 客户端逐帧推送 JPEG，服务端回传检测/手势/表情与互动建议；
 * 识别到「挥手」或稳定目标时，服务端给出带动作与语音的 interaction 事件。
 */
export function usePerceptionSocket(autoConnect = false): PerceptionSocket {
  const [status, setStatus] = useState<PerceptionSocket['status']>('idle')
  const [providers, setProviders] = useState<Record<string, string>>({})
  const [latest, setLatest] = useState<PerceptionMessage | null>(null)
  const [greeting, setGreeting] = useState<{ text: string; drive: AvatarDrive } | null>(null)
  const [interaction, setInteraction] = useState<AvatarInteraction | null>(null)
  const socketRef = useRef<WebSocket | null>(null)

  const disconnect = useCallback(() => {
    if (socketRef.current) {
      socketRef.current.close()
      socketRef.current = null
    }
    setStatus('closed')
    // 断线后旧识别事件已无意义：留着会让用户以为数字人"识别到了什么"却不再更新
    setInteraction(null)
  }, [])

  const connect = useCallback(() => {
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) return
    const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const socket = new WebSocket(`${scheme}://${window.location.host}/api/v1/ws/perception`)
    socketRef.current = socket
    setStatus('connecting')

    socket.onopen = () => setStatus('open')
    socket.onclose = () => setStatus('closed')
    socket.onerror = () => setStatus('closed')
    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data as string)
        if (payload.type === 'ready') {
          setProviders(payload.providers || {})
          return
        }
        if (payload.type !== 'perception') return
        setLatest({ data: payload.data as PerceptionData, suggestion: (payload.suggestion as Suggestion) ?? null })
        if (payload.interaction) {
          setInteraction(payload.interaction as AvatarInteraction)
          return
        }
        // 兼容没有 interaction 字段的旧服务端：把 avatar 问候归一化为交互事件，
        // 避免前后端版本不一致时"挥手没有任何反应"。
        if (payload.avatar) {
          const drive = payload.avatar.drive as AvatarDrive
          setGreeting({ text: payload.avatar.text, drive })
          setInteraction({
            kind: 'greeting',
            text: payload.avatar.text,
            target: null,
            confidence: 0,
            motion: drive?.motion ?? 'wave',
            emotion: drive?.emotion ?? 'cheerful',
            gesture: payload.avatar.gesture ?? null,
            drive: drive ?? null,
          })
        }
      } catch {
        /* 忽略解析失败的帧 */
      }
    }
  }, [])

  useEffect(() => {
    if (autoConnect) connect()
    return () => {
      if (socketRef.current) socketRef.current.close()
    }
  }, [autoConnect, connect])

  const configure = useCallback((options: { withClassify?: boolean; withSegments?: boolean; withOcr?: boolean }) => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify(options))
    }
  }, [])

  const sendFrame = useCallback((blob: Blob) => {
    if (socketRef.current?.readyState !== WebSocket.OPEN) return
    blob
      .arrayBuffer()
      .then((buffer) => socketRef.current?.send(buffer))
      .catch(() => undefined)
  }, [])

  const clearGreeting = useCallback(() => setGreeting(null), [])
  const clearInteraction = useCallback(() => setInteraction(null), [])

  return {
    status,
    providers,
    latest,
    greeting,
    interaction,
    connect,
    disconnect,
    configure,
    sendFrame,
    clearGreeting,
    clearInteraction,
  }
}
