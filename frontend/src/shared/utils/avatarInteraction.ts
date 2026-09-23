/**
 * 工单18 · 数字人交互事件的前端判定（纯函数）
 *
 * 为什么放在 shared/utils 而不是页面里：这些判定决定"要不要开口说话"，
 * 是交互正确性的关键，必须能单测覆盖；写在组件里就只能靠浏览器回归。
 */
import type { AvatarInteraction } from '../../api/client'

/** 低于该置信度的识别不启动播报（与后端协调器 min_confidence 同一口径） */
export const MIN_SPEAK_CONFIDENCE = 0.55

/**
 * 事件去重键：同一目标在冷却窗口内可能被重复下发，问候/推荐类按手势去重。
 * 后半段的文本截断只是兜底——没有目标也没有手势时，仍要能区分不同的话。
 */
export const interactionKey = (event: AvatarInteraction): string =>
  `${event.kind}:${event.target || event.gesture || event.text.slice(0, 24)}`

/**
 * 是否值得为这条事件启动一次播报。
 *
 * 问候类不受置信度门槛限制：手势事件是二值判定（识别到挥手就是挥手），
 * 后端的 0.0~1.0 只是分类器分数，用它卡问候会出现"挥手不理人"。
 */
export const shouldSpeakInteraction = (event: AvatarInteraction | null): boolean => {
  if (!event || !event.text.trim()) return false
  if (event.kind === 'greeting') return true
  return event.confidence >= MIN_SPEAK_CONFIDENCE
}
