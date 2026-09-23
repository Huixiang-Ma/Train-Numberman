/**
 * 工单18 · 数字人交互事件前端纯函数测试（批次：数字人全身视觉交互）
 *
 * 这些判定必须是纯函数、可测：
 *   · 同一目标在冷却窗口内可能被后端重复下发，前端要能识别"同一件事"；
 *   · 低置信度事件后端已转澄清，但网络乱序或旧帧仍可能带来低分事件，前端不能盲播。
 */
import { describe, expect, it } from 'vitest'
import type { AvatarInteraction } from '../../api/client'
import { interactionKey, shouldSpeakInteraction } from './avatarInteraction'

const event: AvatarInteraction = {
  kind: 'explanation',
  text: '这是古建筑。',
  target: '古建筑',
  confidence: 0.92,
  motion: 'explain',
  emotion: 'calm',
  gesture: null,
  drive: null,
}

describe('avatar interaction helpers', () => {
  it('creates a stable key from kind and target', () => {
    expect(interactionKey(event)).toBe('explanation:古建筑')
  })

  it('falls back to gesture then text when no target is present', () => {
    expect(interactionKey({ ...event, target: null, gesture: '挥手' })).toBe('explanation:挥手')
    expect(interactionKey({ ...event, target: null, gesture: null })).toBe('explanation:这是古建筑。')
  })

  it('does not speak an empty or low-confidence event', () => {
    expect(shouldSpeakInteraction({ ...event, text: '' })).toBe(false)
    expect(shouldSpeakInteraction({ ...event, confidence: 0.2 })).toBe(false)
    expect(shouldSpeakInteraction(null)).toBe(false)
  })

  it('allows greeting without a target', () => {
    expect(shouldSpeakInteraction({ ...event, kind: 'greeting', target: null, confidence: 0 })).toBe(true)
  })
})
