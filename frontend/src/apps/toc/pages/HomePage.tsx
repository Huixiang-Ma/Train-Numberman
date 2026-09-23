/**
 * 工单16-20 延伸 · 平台化双端重构（批次 0）
 * ToC 首页：平台定位 + 模块入口 + 建设进度。
 *
 * 批次 0 尚无发现页（批次 1），这里以模块入口承载导航，
 * 并如实标注每个模块的工单依据与当前状态，避免"看起来做完了"。
 */
import { Link, Navigate } from 'react-router-dom'
import EmptyState from '../../../shared/components/EmptyState'
import { READY_ROUTES } from '../../readyRoutes'
import { ROUTES } from '../../routes'

export default function HomePage() {
  // 兼容旧分享链接 `/?share=<token>`（工单19 语义），直接转到新的落地路由
  const legacyShare = new URLSearchParams(window.location.search).get('share')
  if (legacyShare) return <Navigate to={`/s/${legacyShare}`} replace />

  // 列出全部 ToC 模块（仅排除只能从上下文进入的详情页与分享落地页），
  // 使每个模块都可从首页抵达；可用状态直接由 READY_ROUTES 推导，避免硬编码清单漂移。
  const modules = ROUTES.filter(
    (route) => route.side === 'toc' && route.path !== '/park/:id' && route.path !== '/s/:token',
  )
  const ready = new Set(Object.keys(READY_ROUTES))

  return (
    <div className="flex flex-col gap-5">
      <section className="rounded-2xl border border-sand bg-surface/70 px-5 py-6 shadow-panel">
        <div className="font-display text-[22px] leading-tight text-ink">通用文旅数字人导览与内容共创</div>
        <p className="mt-2 max-w-[620px] text-[13px] leading-relaxed text-ink-2">
          面向景区、古城、古镇、古街的通用文旅场景：多模态知识问答、数字人导览、实时互动感知、
          个性化行程策划与 AIGC 纪念内容生成。
        </p>
      </section>

      <section>
        <div className="mb-3 font-display text-[16px] text-ink">功能入口</div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {modules.map((route) => {
            const available = ready.has(route.path)
            return (
              <Link
                key={route.path}
                to={route.path}
                className="group rounded-xl border border-sand bg-surface px-4 py-3.5 transition hover:border-amber/45 hover:shadow-panel"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-display text-[15px] text-ink">{route.label}</span>
                  <span
                    className={`rounded-full border px-2 py-0.5 text-[10.5px] ${
                      available ? 'border-amber/45 bg-amber/10 text-amber-deep' : 'border-sand bg-surface-2 text-ink-4'
                    }`}
                  >
                    {available ? '可用' : '建设中'}
                  </span>
                </div>
                <div className="mt-1 text-[11.5px] text-ink-3">
                  {route.ticket}
                  {route.scene ? ` · ${route.scene}` : ''}
                </div>
              </Link>
            )
          })}
        </div>
      </section>

      <EmptyState
        title="发现页建设中"
        desc="按目的地 / 景区 / 景点分层浏览，支持标签筛选与多模态检索，将在批次 1 提供（需先完成后端数据泛化）。"
        ticket="工单17 §2"
        scene="S1"
      />
    </div>
  )
}
