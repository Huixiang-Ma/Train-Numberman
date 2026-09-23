/**
 * 工单16-20 延伸 · 平台化双端重构（批次 0）
 * ToB 运营控制台布局壳：左侧栏 + 顶栏 + 内容区（桌面优先，冷色令牌）。
 *
 * 注意：全局 body 的背景是暖色径向渐变（src/index.css 工单18 遗留），
 * 本壳必须自带不透明底色并铺满视口，否则暖色会透出、与 ToC 区分不开。
 * 同时不用 `terminal-wrap`：控制台需要在宽屏展开，不做限宽。
 */
import { NavLink, Outlet } from 'react-router-dom'
import { tobNavGroups } from '../../routes'

export default function TobShell() {
  return (
    <div className="min-h-screen bg-cool-bg font-ui text-cool-ink">
      <div className="flex min-h-screen">
        {/* 左侧栏 */}
        <aside className="hidden w-[232px] shrink-0 border-r border-cool-line bg-cool-surface lg:block">
          <div className="flex items-center gap-2 border-b border-cool-line px-4 py-3.5">
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-steel text-[15px] font-semibold text-white">
              运
            </span>
            <div className="leading-tight">
              <div className="text-[13px] font-semibold">运营控制台</div>
              <div className="text-[11px] text-cool-ink-3">文旅创新智脑</div>
            </div>
          </div>

          <nav className="px-2 py-3">
            {tobNavGroups.map((group) => (
              <div key={group.title} className="mb-3">
                <div className="px-2 pb-1 text-[11px] font-medium tracking-wide text-cool-ink-4">{group.title}</div>
                {group.items.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.end}
                    className={({ isActive }) =>
                      `block rounded-lg px-2.5 py-1.5 text-[13px] transition ${
                        isActive ? 'bg-steel/12 font-medium text-steel-deep' : 'text-cool-ink-2 hover:bg-cool-surface-2'
                      }`
                    }
                  >
                    {item.label}
                  </NavLink>
                ))}
              </div>
            ))}
          </nav>
        </aside>

        {/* 右侧内容 */}
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex items-center justify-between gap-3 border-b border-cool-line bg-cool-surface px-4 py-3 sm:px-6">
            <div className="flex items-center gap-2">
              <span className="grid h-7 w-7 place-items-center rounded-lg bg-steel text-[13px] font-semibold text-white lg:hidden">
                运
              </span>
              <span className="text-[13.5px] font-medium">景区运营 · 管理端</span>
            </div>
            <NavLink
              to="/"
              className="rounded-full border border-cool-line bg-cool-surface px-3 py-1 text-[11.5px] text-cool-ink-3 hover:border-steel/40 hover:text-steel-deep"
            >
              返回游客端
            </NavLink>
          </header>

          {/* 窄屏下侧栏不可用，退化为顶部横向滚动导航（沿用现有 .scroll-x） */}
          <nav className="scroll-x border-b border-cool-line bg-cool-surface px-4 py-2 lg:hidden">
            {tobNavGroups.flatMap((group) => group.items).map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `rounded-full border px-3 py-1 text-[12px] ${
                    isActive
                      ? 'border-steel/45 bg-steel/10 text-steel-deep'
                      : 'border-cool-line bg-cool-surface-2 text-cool-ink-3'
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <main className="min-w-0 flex-1 px-4 py-5 sm:px-6">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  )
}
