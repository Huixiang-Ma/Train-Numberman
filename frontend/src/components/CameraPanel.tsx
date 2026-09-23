import { useCallback, useEffect, useRef, useState } from 'react'
import type { PerceptionSocket } from '../hooks/usePerceptionSocket'

const FRAME_INTERVAL_MS = 700

interface Props {
  socket: PerceptionSocket
  /**
   * 嵌入数字人舞台时为 true：去掉卡片边框与标题，预览收成小窗，
   * 只保留采集能力。识别结果由数字人本体表达，不再单独成面板。
   */
  embedded?: boolean
}

/**
 * 工单18 · 实时行为与环境感知
 * 摄像头逐帧推送 → 服务端 YOLO11 + MediaPipe 推理 → 回传检测框与手势/表情。
 * 摄像头不可用时，可上传一张含手势的图片走同一条感知链路。
 */
export default function CameraPanel({ socket, embedded = false }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const timerRef = useRef<number | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const [cameraOn, setCameraOn] = useState(false)
  const [message, setMessage] = useState<string>('')

  const capture = useCallback((): Promise<Blob | null> => {
    const video = videoRef.current
    const canvas = canvasRef.current
    if (!video || !canvas || !video.videoWidth) return Promise.resolve(null)
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    const context = canvas.getContext('2d')
    if (!context) return Promise.resolve(null)
    context.drawImage(video, 0, 0, canvas.width, canvas.height)
    return new Promise((resolve) => canvas.toBlob((blob) => resolve(blob), 'image/jpeg', 0.72))
  }, [])

  const stopCamera = useCallback(() => {
    if (timerRef.current) {
      window.clearInterval(timerRef.current)
      timerRef.current = null
    }
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    if (videoRef.current) videoRef.current.srcObject = null
    setCameraOn(false)
  }, [])

  const startCamera = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 400 }, audio: false })
      streamRef.current = stream
      if (videoRef.current) {
        videoRef.current.srcObject = stream
        await videoRef.current.play().catch(() => undefined)
      }
      setCameraOn(true)
      setMessage('')
      timerRef.current = window.setInterval(async () => {
        const blob = await capture()
        if (blob) socket.sendFrame(blob)
      }, FRAME_INTERVAL_MS)
    } catch (error) {
      setMessage(`无法访问摄像头（${(error as Error).name}），可改用下方「上传图像感知」`)
    }
  }, [capture, socket])

  useEffect(() => () => stopCamera(), [stopCamera])

  useEffect(() => {
    if (!cameraOn) return
    socket.configure({ withClassify: false, withSegments: false, withOcr: false })
  }, [cameraOn, socket])

  const onUpload = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0]
      if (!file) return
      socket.sendFrame(file)
      setMessage(`已发送「${file.name}」进行感知分析`)
      event.target.value = ''
    },
    [socket],
  )

  const detections = socket.latest?.data.detections ?? []
  const boxes = detections.filter((item) => (item.box?.[2] ?? 0) > 0.01)

  return (
    <section className={embedded ? '' : 'rounded-2xl border border-sand bg-surface p-5 shadow-panel'}>
      {!embedded && (
        <header className="mb-3 flex items-baseline justify-between gap-3">
          <h2 className="font-display text-base">实时行为感知</h2>
          <span className="text-[11.5px] text-ink-4">
            {socket.status === 'open' ? '感知已连接' : socket.status === 'connecting' ? '连接中…' : '感知未连接'}
          </span>
        </header>
      )}

      <div
        className={`relative overflow-hidden rounded-xl border border-sand bg-[#2A1D14] ${
          embedded ? 'h-[132px] w-full max-w-[240px]' : 'aspect-[16/10]'
        }`}
      >
        <video ref={videoRef} autoPlay muted playsInline className="h-full w-full object-contain" />
        <canvas ref={canvasRef} className="hidden" />
        {!cameraOn && (
          <div className="absolute inset-0 grid place-content-center px-6 text-center text-[12.5px] leading-relaxed text-[#F6E4CE]/70">
            {embedded ? '开启摄像头，让数字人看见你' : '点击「开启摄像头」进行手势互动'}
            {!embedded && (
              <>
                <br />
                或上传一张含手势/人像的图片进行感知
              </>
            )}
          </div>
        )}
        {boxes.map((item, index) => (
          <div
            key={`${item.track_id ?? 'd'}-${index}`}
            className="pointer-events-none absolute rounded border-[1.5px] border-[#D9A05F]"
            style={{
              left: `${item.box[0] * 100}%`,
              top: `${item.box[1] * 100}%`,
              width: `${item.box[2] * 100}%`,
              height: `${item.box[3] * 100}%`,
            }}
          >
            <span className="absolute -top-[19px] left-0 whitespace-nowrap rounded bg-clay/90 px-1.5 py-px text-[10.5px] text-[#FFF3E8]">
              {item.label}
              {item.track_id != null ? ` #${item.track_id}` : ''}
            </span>
          </div>
        ))}
      </div>

      <div className={embedded ? 'mt-2 flex flex-wrap gap-1.5' : 'mt-3 flex flex-wrap gap-2'}>
        <button
          type="button"
          onClick={() => (cameraOn ? stopCamera() : startCamera())}
          className={`rounded-full bg-amber text-[#FFF8EC] transition hover:bg-amber-deep ${
            embedded ? 'px-3 py-1.5 text-[12px]' : 'px-4 py-2 text-[13px]'
          }`}
        >
          {cameraOn ? '关闭摄像头' : '开启摄像头'}
        </button>
        <button
          type="button"
          onClick={() => socket.connect()}
          disabled={socket.status === 'open'}
          className={`rounded-full border border-sand bg-surface text-ink-2 transition hover:border-amber hover:text-amber disabled:opacity-50 ${
            embedded ? 'px-3 py-1.5 text-[12px]' : 'px-4 py-2 text-[13px]'
          }`}
        >
          连接感知
        </button>
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          className={`rounded-full border border-sand bg-surface text-ink-2 transition hover:border-amber hover:text-amber ${
            embedded ? 'px-3 py-1.5 text-[12px]' : 'px-4 py-2 text-[13px]'
          }`}
        >
          上传图像感知
        </button>
        <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={onUpload} />
      </div>

      {message && <p className="mt-2 text-[11.5px] text-ink-3">{message}</p>}
    </section>
  )
}
