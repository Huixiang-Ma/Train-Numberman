/**
 * 工单18 §1 · 语音输入（游客端录音）
 *
 * 为什么需要补：后端 `/dialog/multimodal` 一直支持 `audio` 字段，但游客端**从未实现过录音**，
 * 因此工单18 要求的"语音提问"和工单20 的场景 2/11/17 实际上只有文字入口。
 *
 * 实现取舍：
 *   - 用浏览器原生 `MediaRecorder`，不引入录音库（docs/08 §4.3 的既有取向）
 *   - 必须正确处理三种不可用情形：浏览器不支持、用户拒绝授权、非安全上下文
 *     —— 静默失败会让用户以为"点了没反应"，所以状态要显式暴露给界面
 */
import { useCallback, useEffect, useRef, useState } from 'react'

export type RecorderState = 'unsupported' | 'idle' | 'requesting' | 'recording' | 'denied' | 'error'

export type Recording = { blob: Blob; mime: string; seconds: number }

export function useAudioRecorder() {
  const [state, setState] = useState<RecorderState>('idle')
  const [seconds, setSeconds] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const streamRef = useRef<MediaStream | null>(null)
  const timerRef = useRef<number | null>(null)
  const secondsRef = useRef(0)

  // 环境探测：非安全上下文（http 且非 localhost）或旧浏览器上没有录音能力
  useEffect(() => {
    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setState('unsupported')
    }
  }, [])

  const cleanup = useCallback(() => {
    if (timerRef.current) {
      window.clearInterval(timerRef.current)
      timerRef.current = null
    }
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    recorderRef.current = null
  }, [])

  useEffect(() => cleanup, [cleanup])

  const start = useCallback(async () => {
    if (state === 'unsupported' || recorderRef.current) return
    setError(null)
    setState('requesting')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      const recorder = new MediaRecorder(stream)
      chunksRef.current = []
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data)
      }
      recorder.start()
      recorderRef.current = recorder
      secondsRef.current = 0
      setSeconds(0)
      setState('recording')
      timerRef.current = window.setInterval(() => {
        secondsRef.current += 1
        setSeconds(secondsRef.current)
      }, 1000)
    } catch (caught) {
      cleanup()
      const name = caught instanceof Error ? caught.name : ''
      // NotAllowedError = 用户拒绝；其余（NotFoundError 等）按设备/环境问题提示
      setState(name === 'NotAllowedError' ? 'denied' : 'error')
      setError(caught instanceof Error ? caught.message : String(caught))
    }
  }, [cleanup, state])

  const stop = useCallback(async (): Promise<Recording | null> => {
    const recorder = recorderRef.current
    if (!recorder) return null
    const mime = recorder.mimeType || 'audio/webm'
    const duration = secondsRef.current
    const blob = await new Promise<Blob>((resolve) => {
      recorder.addEventListener('stop', () => resolve(new Blob(chunksRef.current, { type: mime })), { once: true })
      recorder.stop()
    })
    cleanup()
    setState('idle')
    setSeconds(0)
    if (blob.size === 0) {
      setError('没有录到声音，请检查麦克风后重试')
      return null
    }
    return { blob, mime, seconds: duration }
  }, [cleanup])

  const reset = useCallback(() => {
    cleanup()
    setError(null)
    setState('idle')
    setSeconds(0)
  }, [cleanup])

  return { state, seconds, error, start, stop, reset }
}
