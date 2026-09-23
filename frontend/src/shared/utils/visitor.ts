/**
 * 工单16-20 延伸 · 匿名游客标识（批次 5）
 *
 * 本项目**没有游客账号体系**（与 share / creation 的既有取向一致：游客端全程免登录）。
 * 但「我的订单」「我的工单」需要一个稳定的归集键，否则刷新页面就找不到自己的单据。
 *
 * 因此用一枚存在 localStorage 的随机串充当身份。它刻意满足三点：
 *   1. **不含任何个人信息**：纯随机，无法反推到人；
 *   2. **不是安全边界**：知道这串就能看到对应单据，所以后端不把它当凭证，
 *      取单据时也只按这个随机串过滤，不返回手机号明文（已脱敏）；
 *   3. **可清除**：用户清掉浏览器数据即等同于注销，无需后端配合。
 *
 * 为什么用 localStorage 而登录态用 sessionStorage：订单需要跨会话可见
 * （今天下单、明天来取票），而运营令牌恰恰不该跨会话留存。两者诉求相反，故分开存。
 */
const VISITOR_KEY = 'wenlv.visitor.ref'

function randomRef(): string {
  // crypto.randomUUID 在非安全上下文（http 局域网）不可用，故做降级
  const globalCrypto = window.crypto
  if (globalCrypto?.randomUUID) return globalCrypto.randomUUID().replace(/-/g, '')

  const bytes = new Uint8Array(16)
  if (globalCrypto?.getRandomValues) {
    globalCrypto.getRandomValues(bytes)
  } else {
    for (let i = 0; i < bytes.length; i += 1) bytes[i] = Math.floor(Math.random() * 256)
  }
  return Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('')
}

export function visitorRef(): string {
  try {
    const existing = window.localStorage.getItem(VISITOR_KEY)
    if (existing) return existing
    const created = randomRef()
    window.localStorage.setItem(VISITOR_KEY, created)
    return created
  } catch {
    // 隐私模式下存储不可用：退化为每次调用生成新串，
    // 「我的订单」会失效但不至于让下单本身失败。
    return randomRef()
  }
}
