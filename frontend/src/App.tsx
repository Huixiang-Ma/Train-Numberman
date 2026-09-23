/**
 * 工单16-20 延伸 · 平台化双端重构（批次 0）
 * 应用入口：仅做路由装配。
 *
 * 原来 217 行的单页已迁移为 apps/toc/pages/GuidePage.tsx（路由 /guide）。
 * 两端分流靠路径前缀：`/admin` 走 ToB 控制台，其余走 ToC 游客端。
 * 全量路由来自 routes.ts。
 *
 * 截至批次 6，注册表中的 19 条路由**已全部实现**，renderRoute 的 EmptyState 分支
 * 不再有实际命中者；它作为安全网保留（新增路由但忘了接线时，页面会如实说明
 * 而不是白屏），并由 readyRoutes.test.tsx 的「全覆盖」断言守住这一点。
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
          {/*
            控制台内的未知路径兜底。缺了它，/admin/typo 会匹配到壳但匹配不到任何子路由，
            渲染出"只有侧栏、内容区空白"的页面 —— 现场会以为系统坏了。
            ToC 侧的未知路径由最外层的 * 兜回首页。
          */}
          <Route
            path="*"
            element={
              <EmptyState
                tone="cool"
                title="控制台页面不存在"
                desc="该路径未在控制台注册。请从左侧栏选择功能，或返回控制台总览。"
              />
            }
          />
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
