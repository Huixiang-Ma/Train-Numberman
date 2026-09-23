/**
 * 工单16-20 延伸 · 平台化双端重构（批次 0）
 * 「已实现路由 → 真实页面组件」的映射表。
 *
 * 未出现在本表中的路由将由 App.tsx 渲染 EmptyState（建设中），
 * 其标题与工单依据取自 routes.ts，因此不会出现无说明的空白页。
 * 后续批次只需往本表加一项，即可把某个模块从"建设中"切换为真实页面。
 */
import type { ReactElement } from 'react'
import ActivityPage from './toc/pages/ActivityPage'
import AskPage from './toc/pages/AskPage'
import CreatePage from './toc/pages/CreatePage'
import ExplorePage from './toc/pages/ExplorePage'
import GuidePage from './toc/pages/GuidePage'
import HomePage from './toc/pages/HomePage'
import MapPage from './toc/pages/MapPage'
import MePage from './toc/pages/MePage'
import ParkDetailPage from './toc/pages/ParkDetailPage'
import PlanPage from './toc/pages/PlanPage'
import ShareLandingPage from './toc/pages/ShareLandingPage'
import ContentPage from './tob/pages/ContentPage'
import KbPage from './tob/pages/KbPage'
import LoginPage from './tob/pages/LoginPage'
import OverviewPage from './tob/pages/OverviewPage'
import ParksPage from './tob/pages/ParksPage'
import ReviewPage from './tob/pages/ReviewPage'
import UsersPage from './tob/pages/UsersPage'

export const READY_ROUTES: Record<string, ReactElement> = {
  // ToC
  '/': <HomePage />,
  '/explore': <ExplorePage />,
  '/park/:id': <ParkDetailPage />,
  '/guide': <GuidePage />,
  '/ask': <AskPage />,
  '/plan': <PlanPage />,
  '/create': <CreatePage />,
  '/activity': <ActivityPage />,
  '/map': <MapPage />,
  '/me': <MePage />,
  '/s/:token': <ShareLandingPage />,
  // ToB
  // 登录页虽在 /admin 前缀下，但由 App.tsx 装配为 TobShell 的兄弟路由（免守卫）
  '/admin/login': <LoginPage />,
  '/admin': <OverviewPage />,
  '/admin/kb': <KbPage />,
  '/admin/content': <ContentPage />,
  '/admin/parks': <ParksPage />,
  '/admin/review': <ReviewPage />,
  '/admin/users': <UsersPage />,
}
