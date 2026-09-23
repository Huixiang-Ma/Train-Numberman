/**
 * 工单16-20 延伸 · 平台化双端重构（批次 0）
 * ToC 游客端布局壳：移动端底部 Tab + 桌面端顶部导航。
 *
 * 多端依据 docs/06 §4.1（Web / App / 小程序 / 自助终端）：
 * 沿用现有 `terminal-wrap`（大屏限宽）与 `--wenlv-safe-bottom`（手势条安全区），
 * 不重新发明一套适配规则。
 */
import { NavLink, Outlet } from 'react-router-dom'
import { tocNav } from '../../routes'

export default function TocShell() {
  return (
    <div className="min-h-screen terminal-wrap">
      <header className="sticky top-0 z-20 border-b border-sand bg-paper/85 backdrop-blur">
        <div className="mx-auto flex max-w-[1180px] items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <NavLink to="/" className="flex items-center gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-amber-soft to-amber-deep font-display text-lg text-[#FFF8EC]">
              智
            </span>
            <span className="font-display text-[17px] leading-tight">文旅创新智脑</span>
          </NavLink>

          <nav className="hidden items-center gap-1 md:flex">
            {tocNav.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `rounded-lg px-3 py-1.5 text-[13px] transition ${
                    isActive ? 'bg-amber/12 text-amber-deep' : 'text-ink-2 hover:bg-surface-2'
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <NavLink
            to="/admin"
            className="rounded-full border border-sand bg-surface px-3 py-1 text-[11.5px] text-ink-3 hover:border-amber/40 hover:text-amber-deep"
          >
            运营控制台
          </NavLink>
        </div>
      </header>

      {/* 底部 Tab 是移动端的固定层，内容区为其预留内距（md 以上取消） */}
      <main className="mx-auto w-full max-w-[1180px] px-4 pb-24 pt-5 sm:px-6 md:pb-10">
        <Outlet />
      </main>

      <nav
        className="fixed inset-x-0 bottom-0 z-20 border-t border-sand bg-surface/95 backdrop-blur md:hidden"
        style={{ paddingBottom: 'var(--wenlv-safe-bottom)' }}
      >
        <div className="flex">
          {tocNav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px] ${
                  isActive ? 'text-amber-deep' : 'text-ink-3'
                }`
              }
            >
              <span className="text-[15px] leading-none" aria-hidden>
                {item.glyph}
              </span>
              {item.label}
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  )
}
