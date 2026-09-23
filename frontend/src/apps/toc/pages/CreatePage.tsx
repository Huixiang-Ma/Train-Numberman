/**
 * 工单19 §2 · ToC 专属纪念内容生成（S5）
 *
 * 页面结构上刻意"一页一职"：
 *   /plan     行程策划（S4）
 *   /create   纪念内容（S5）  ← 本页
 *   /activity 活动体验（S6）
 *   /map      导览地图
 * 原先这三块被 CreativeStudio 以标签页捆在一处；拆成独立路由后，
 * CreativeStudio 的职责已被这三条路由完全覆盖，故不再挂载（文件保留未删，见执行账本）。
 */
import CreationPanel from '../../../components/CreationPanel'

export default function CreatePage() {
  return (
    <div className="flex flex-col gap-4">
      <section className="rounded-2xl border border-sand bg-surface/70 px-5 py-4 shadow-panel">
        <h1 className="font-display text-[21px] leading-tight text-ink">纪念内容创作</h1>
        <p className="mt-1 text-[12.5px] leading-relaxed text-ink-3">
          把旅行照片变成艺术化纪念照、明信片或虚拟合影；也可以生成旅行短片与旅行日记。
        </p>
      </section>

      <CreationPanel />
    </div>
  )
}
