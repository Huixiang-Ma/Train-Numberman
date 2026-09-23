/**
 * 工单18 · 数字人舞台内的交互反馈层
 *
 * 设计取向（用户已确认）：识别结果**不再单独成面板**，而是由数字人本体表达——
 * 字幕气泡说数字人正在说的话，动作/表情/语音由 AvatarStage 与 playDrive 呈现；
 * 摄像头、上传与连接作为舞台内的悬浮控件，识别目标只作为气泡副文本。
 *
 * 这里刻意只做"呈现"，不做识别判定：事件由后端 interaction 决定，
 * 前端仅负责不重复播报与降级提示（见 shared/utils/avatarInteraction.ts）。
 */
import type { AvatarInteraction } from '../api/client'
import type { PerceptionSocket } from '../hooks/usePerceptionSocket'
import CameraPanel from './CameraPanel'

interface Props {
  interaction: AvatarInteraction | null
  socket: PerceptionSocket
  speaking: boolean
}

/** 事件类型 → 中文标签（气泡眉标，让游客知道数字人此刻在做什么） */
const KIND_LABEL: Record<string, string> = {
  greeting: '主动问候',
  explanation: '景点讲解',
  clarification: '需要确认',
  guidance: '路线指引',
  answer: '回答',
  encouragement: '回应',
  recommendation: '推荐',
}

export default function AvatarInteractionOverlay({ interaction, socket, speaking }: Props) {
  const caption = interaction?.text?.trim() ?? ''
  const targetLabel = interaction?.target
    ? `${interaction.target} · ${Math.round((interaction.confidence ?? 0) * 100)}%`
    : null

  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-0 flex flex-col gap-2 p-3">
      {caption && (
        <div
          aria-live="polite"
          className="pointer-events-auto animate-rise rounded-2xl border border-amber/30 bg-surface/92 px-4 py-2.5 shadow-panel backdrop-blur"
        >
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <span className="text-[11px] font-medium text-amber-deep">
              {KIND_LABEL[interaction?.kind ?? ''] ?? '数字人'}
            </span>
            {targetLabel && <span className="text-[11px] text-ink-4">识别 · {targetLabel}</span>}
          </div>
          <p className="mt-1 text-[13.5px] leading-relaxed text-ink">{caption}</p>
        </div>
      )}

      <div className="pointer-events-auto flex flex-wrap items-end justify-between gap-3 rounded-2xl border border-sand bg-surface/85 p-3 backdrop-blur">
        <div className="flex flex-col gap-1.5">
          <span className="text-[12px] text-ink-2">视觉感知已嵌入数字人</span>
          <span className="text-[11px] leading-relaxed text-ink-4">
            {socket.status === 'open'
              ? '感知已连接：对着摄像头挥手，或让镜头对准景物'
              : socket.status === 'connecting'
                ? '感知连接中…'
                : '感知未连接：点「连接感知」后可手势互动'}
          </span>
          <span
            className={`w-fit rounded-full border px-2.5 py-0.5 text-[11px] ${
              speaking ? 'border-clay bg-clay/12 text-clay' : 'border-sand bg-surface text-ink-3'
            }`}
          >
            {speaking ? '播报中' : '待机'}
          </span>
        </div>
        <CameraPanel socket={socket} embedded />
      </div>
    </div>
  )
}
