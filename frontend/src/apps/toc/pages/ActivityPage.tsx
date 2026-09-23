/**
 * 工单19 §3 · ToC 活动与体验推荐（S6）
 *
 * 复用既有 ActivityPanel（工单19 实现，不动内部逻辑），汇入 ToC 路由。
 * 后端 /activity/recommend 支持按坐标做距离排序，本机无定位时自动退回无语义距离的推荐。
 */
import ActivityPanel from '../../../components/ActivityPanel'

export default function ActivityPage() {
  return (
    <div className="flex flex-col gap-4">
      <section className="rounded-2xl border border-sand bg-surface/70 px-5 py-4 shadow-panel">
        <h1 className="font-display text-[21px] leading-tight text-ink">活动与体验</h1>
        <p className="mt-1 text-[12.5px] leading-relaxed text-ink-3">
          按兴趣推荐可参与的活动与体验项目，并可一键生成参与攻略与流程图。
        </p>
      </section>

      <ActivityPanel />
    </div>
  )
}
