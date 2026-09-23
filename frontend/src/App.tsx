/**
 * 工单16-20 延伸 · 平台化双端重构（批次 0）
 * 应用入口：仅做路由装配。
 *
 * 原来 217 行的单页已迁移为 apps/toc/pages/GuidePage.tsx（路由 /guide）。
 * 两端分流靠路径前缀：`/admin` 走 ToB 控制台，其余走 ToC 游客端。
 * 全量路由来自 routes.ts，未实现的模块渲染 EmptyState 并标注工单依据。
 *
 * 注意 index 路由的写法：react-router v6 中 index 路由**不得**同时带 path，
 * 否则会与父路由的 path 冲突；因此壳根单独用 <Route index>，其余子路由用相对路径。
 */
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { READY_ROUTES } from './apps/readyRoutes'
import { ROUTES, findRoute } from './apps/routes'
import TocShell from './apps/toc/shell/TocShell'
import TobShell from './apps/tob/shell/TobShell'
import EmptyState from './shared/components/EmptyState'
import RequireAuth from './shared/components/RequireAuth'

function renderRoute(path: string) {
  const ready = READY_ROUTES[path]
  if (ready) return ready
  const route = findRoute(path)
  return (
    <EmptyState
      title={`${route?.label ?? '该模块'}建设中`}
      desc="该模块属于后续批次，路由与导航已就绪，页面实现后将直接替换本提示。"
      ticket={route?.ticket}
      scene={route?.scene}
      tone={path.startsWith('/admin') ? 'cool' : 'warm'}
    />
  )
}

export default function App() {
  const tocRoutes = ROUTES.filter((route) => route.side === 'toc')
  const tobRoutes = ROUTES.filter((route) => route.side === 'tob')

  return (
    <BrowserRouter>
      <Routes>
        {/*
          登录页必须是 /admin 壳的**兄弟**路由而不是子路由：
          挂在壳内会被 RequireAuth 挡住（未登录就看不到登录页），
          或反过来渲染进控制台侧栏里。批次 0 最终审查已标出这一项。
        */}
        <Route path="/admin/login" element={renderRoute('/admin/login')} />

        {/* ToB 运营控制台（桌面优先，冷色） */}
        <Route
          path="/admin"
          element={
            <RequireAuth>
              <TobShell />
            </RequireAuth>
          }
        >
          <Route index element={renderRoute('/admin')} />
          {tobRoutes
            .filter((route) => route.path !== '/admin' && route.path !== '/admin/login')
            .map((route) => (
              <Route key={route.path} path={route.path.replace('/admin/', '')} element={renderRoute(route.path)} />
            ))}
        </Route>

        {/* ToC 游客端（移动优先，暖色） */}
        <Route path="/" element={<TocShell />}>
          <Route index element={renderRoute('/')} />
          {tocRoutes
            .filter((route) => route.path !== '/')
            .map((route) => (
              <Route key={route.path} path={route.path.slice(1)} element={renderRoute(route.path)} />
            ))}
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
