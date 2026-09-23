/**
 * 工单16 §5 · 运营端登录态（批次 4）
 *
 * 为什么用 sessionStorage 而不是 localStorage：
 * 控制台登出后不应残留令牌；会话级存储关闭标签页即失效，
 * 对内部运营后台是更合适的默认（游客端不涉及令牌，不受影响）。
 *
 * 为什么不做 JWT 解析取角色：角色由后端在响应里回传（TokenOut.role），
 * 前端自行解码 JWT 只会引入一份与后端可能不一致的判定逻辑。
 */
const TOKEN_KEY = 'wenlv.tob.token'
const ROLE_KEY = 'wenlv.tob.role'
const NAME_KEY = 'wenlv.tob.name'

export function getToken(): string | null {
  try {
    return window.sessionStorage.getItem(TOKEN_KEY)
  } catch {
    // 隐私模式 / 禁用存储时不应让整个控制台崩掉，降级为"未登录"
    return null
  }
}

export function getRole(): string {
  try {
    return window.sessionStorage.getItem(ROLE_KEY) ?? ''
  } catch {
    return ''
  }
}

export function getOperator(): string {
  try {
    return window.sessionStorage.getItem(NAME_KEY) ?? ''
  } catch {
    return ''
  }
}

export function saveSession(token: string, role: string, operator: string): void {
  try {
    window.sessionStorage.setItem(TOKEN_KEY, token)
    window.sessionStorage.setItem(ROLE_KEY, role)
    window.sessionStorage.setItem(NAME_KEY, operator)
  } catch {
    /* 存储不可用时仅当前标签页有效，不阻断登录流程本身 */
  }
}

export function clearSession(): void {
  try {
    window.sessionStorage.removeItem(TOKEN_KEY)
    window.sessionStorage.removeItem(ROLE_KEY)
    window.sessionStorage.removeItem(NAME_KEY)
  } catch {
    /* 同上 */
  }
}

/** RBAC 四级角色（与后端 core/security.py 的 ROLE_ORDER 同序） */
export const ROLE_LABEL: Record<string, string> = {
  guest: '游客',
  editor: '运营',
  expert: '专家',
  admin: '管理员',
}

export const ROLE_ORDER: Record<string, number> = { guest: 0, editor: 1, expert: 2, admin: 3 }

/** 当前角色是否达到 minRole（用于前端隐藏无权操作，后端仍会独立鉴权） */
export function roleAtLeast(minRole: string): boolean {
  return (ROLE_ORDER[getRole()] ?? -1) >= (ROLE_ORDER[minRole] ?? 99)
}
