/**
 * 工单16 §5 · 控制台路由守卫（批次 4）
 *
 * 为什么守卫只把「登录页」排除在外：/admin/login 若挂在 TobShell 之下，
 * 会被守卫挡住（未登录就不能看登录页），或反过来渲染进控制台侧栏里。
 * 因此登录页在 App.tsx 中与 TobShell 平级，不经过本组件。
 *
 * 前端守卫只是体验层：真正的鉴权在后端（require_editor / require_role）。
 * 前端不做权限判定的唯一事实源，避免与后端不一致时"看起来能点、点了报错"。
 */
import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { getToken } from '../utils/auth'

export default function RequireAuth({ children }: { children: ReactNode }) {
  const location = useLocation()
  if (!getToken()) {
    // 记录来源路径，登录成功后直接回到用户原本要去的页面
    return <Navigate to="/admin/login" replace state={{ from: location.pathname }} />
  }
  return <>{children}</>
}
