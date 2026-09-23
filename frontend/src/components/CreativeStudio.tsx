import { useState } from 'react'
import ActivityPanel from './ActivityPanel'
import CreationPanel from './CreationPanel'
import ItineraryPanel from './ItineraryPanel'
import SharePanel from './SharePanel'

/** 工单19 · 创意策划与内容生成工作台（阶段四入口，四个功能区切换） */

type Tab = 'itinerary' | 'creation' | 'activity' | 'share'

const TABS: { key: Tab; label: string; caption: string }[] = [
  { key: 'itinerary', label: '线路策划', caption: '兴趣 · 主题 · 时长' },
  { key: 'creation', label: '纪念内容', caption: '照片 · 明信片 · 短片' },
  { key: 'activity', label: '活动推荐', caption: '位置 · 兴趣 · 攻略' },
  { key: 'share', label: '我的创作', caption: '保存 · 下载 · 分享' },
]

export default function CreativeStudio() {
  const [tab, setTab] = useState<Tab>('itinerary')

  return (
    <section className="rounded-2xl border border-sand bg-surface-2/60 p-4 shadow-panel">
      <header className="mb-4 flex flex-wrap items-center justify-between gap-3 px-1">
        <div>
          <h2 className="font-display text-[17px] text-ink">创意策划与内容生成</h2>
          <div className="text-[11.5px] text-ink-3">
            阶段四（工单19）· 把检索到的知识变成可游、可玩、可带走、可分享的个性化内容
          </div>
        </div>
        {/* 移动端用横向滚动而不是换行：四个标签换行会占掉两行高度、挤压首屏 */}
        <div className="scroll-x w-full sm:w-auto sm:flex-wrap">
          {TABS.map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => setTab(item.key)}
              className={`rounded-full border px-3.5 py-1.5 text-left text-[12.5px] transition ${
                tab === item.key
                  ? 'border-amber bg-amber text-[#FFF8EC]'
                  : 'border-sand bg-surface text-ink-2 hover:border-amber hover:text-amber'
              }`}
            >
              {item.label}
              <span className={`ml-1.5 text-[10.5px] ${tab === item.key ? 'text-[#FFF8EC]/70' : 'text-ink-4'}`}>
                {item.caption}
              </span>
            </button>
          ))}
        </div>
      </header>

      <div className="[&>section]:shadow-none">
        {tab === 'itinerary' && <ItineraryPanel />}
        {tab === 'creation' && <CreationPanel />}
        {tab === 'activity' && <ActivityPanel />}
        {tab === 'share' && <SharePanel />}
      </div>
    </section>
  )
}
