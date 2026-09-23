/**
 * 工单16 §5 · 用户与权限（批次 4）
 *
 * 这一页刻意**不画一个假的用户列表**。后端 `core/security.py` 的 authenticate()
 * 目前是内置账号（环境变量 ADMIN_USERNAME / ADMIN_PASSWORD），没有用户表可列；
 * 凭空渲染几个张三李四会让运营误以为后台已有账号体系。
 * 因此本页回显的是三件真实存在的东西：
 *   1. 当前会话（账号 / 角色 / 存储方式）
 *   2. RBAC 四级角色的能力边界
 *   3. 后端接口的**实际**鉴权实况（逐个核对代码得出，不是设计意图）
 *
 * 第 3 项特意区分了"已定义"与"已启用"：ROLE_EXPERT 在 ROLE_ORDER 里存在，
 * 但全项目没有任何守卫使用它 —— 也就是说现在专家与运营的实际权限完全相同。
 * 这种落差必须显式说出来，否则权限页就是在骗人。
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import PageHeader from '../../../shared/components/PageHeader'
import { ROLE_LABEL, ROLE_ORDER, clearSession, getOperator, getRole } from '../../../shared/utils/auth'
import { TONE_CLASS } from '../../../shared/utils/tone'

/** 受保护接口清单：逐条对照后端 api/v1 与 api/deps.py 得出 */
const GUARDED = [
  { path: 'POST /media/upload', min: 'editor' },
  { path: 'POST /kb/ingest', min: 'editor' },
  { path: 'POST /kb/ingest/file', min: 'editor' },
  { path: 'GET /kb', min: 'editor' },
  { path: 'PUT /kb/{chunk_id}', min: 'editor' },
  { path: 'DELETE /kb/{chunk_id}', min: 'editor' },
  { path: 'GET /audit/logs', min: 'editor' },
  { path: 'GET /audit/compliance', min: 'editor' },
]

/** 能力边界：按角色递增，逐条对应上表与游客端可用接口 */
const CAPABILITIES: { role: string; items: string[] }[] = [
  {
    role: 'guest',
    items: ['检索与问答（/query、/dialog、/search/*）', '数字人与感知（/avatar、/perception）', '行程与创作（/itinerary、/activity、/create/*）', '浏览目的地与景区（/destination、/park）'],
  },
  {
    role: 'editor',
    items: ['游客全部能力', '知识库写入：入库 / 编辑 / 删除', '知识库读取（列表与详情）', '多媒体上传', '审计日志与合规自查'],
  },
  {
    role: 'expert',
    items: ['运营全部能力', '（预留）内容审核权限', '当前无接口使用该等级'],
  },
  {
    role: 'admin',
    items: ['专家全部能力', '（预留）系统级配置与账号管理', '当前内置账号即管理员等级'],
  },
]

export default function UsersPage() {
  const navigate = useNavigate()
  const [showToken, setShowToken] = useState(false)
  const operator = getOperator()
  const role = getRole()

  const logout = () => {
    clearSession()
    navigate('/admin/login', { replace: true })
  }

  return (
    <div>
      <PageHeader
        tone="cool"
        title="用户与权限"
        desc="RBAC 四级角色与后端接口的实际鉴权范围（工单16 §5）"
        extra={
          <button
            onClick={logout}
            className="rounded-lg border border-clay/45 bg-clay/12 px-3 py-1.5 text-[12.5px] text-clay-deep"
          >
            退出登录
          </button>
        }
      />

      {/* 当前会话 */}
      <section className="mb-6">
        <h2 className="mb-2.5 text-[13px] font-medium text-cool-ink">当前会话</h2>
        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-3">
          <div className="rounded-xl border border-cool-line bg-cool-surface p-3.5 shadow-console">
            <div className="text-[11.5px] text-cool-ink-3">账号</div>
            <div className="mt-0.5 text-[15px] font-semibold text-cool-ink">{operator || '—'}</div>
          </div>
          <div className="rounded-xl border border-cool-line bg-cool-surface p-3.5 shadow-console">
            <div className="text-[11.5px] text-cool-ink-3">角色</div>
            <div className="mt-0.5 flex items-center gap-2">
              <span className="text-[15px] font-semibold text-cool-ink">{ROLE_LABEL[role] ?? role ?? '—'}</span>
              <span className={`rounded-full border px-2 py-0.5 text-[10.5px] ${TONE_CLASS.ok}`}>
                等级 {ROLE_ORDER[role] ?? '—'}
              </span>
            </div>
          </div>
          <div className="rounded-xl border border-cool-line bg-cool-surface p-3.5 shadow-console">
            <div className="text-[11.5px] text-cool-ink-3">令牌</div>
            <div className="mt-0.5 flex items-center gap-2">
              <span className="text-[15px] font-semibold text-cool-ink">已签发</span>
              <button onClick={() => setShowToken((value) => !value)} className="text-[11.5px] text-steel-deep underline">
                {showToken ? '隐藏' : '说明'}
              </button>
            </div>
          </div>
        </div>
        {showToken && (
          <div className="mt-2.5 rounded-lg border border-cool-line bg-cool-bg px-3.5 py-2.5 text-[11.5px] leading-relaxed text-cool-ink-3">
            JWT 存放于 <code className="text-cool-ink-2">sessionStorage</code>（会话级，关闭标签页即失效），
            由 <code className="text-cool-ink-2">api/client.ts</code> 自动注入到每个请求的
            <code className="text-cool-ink-2"> Authorization: Bearer</code> 头。
            本页不展示令牌原文，避免出现在截图与录屏里。
          </div>
        )}
      </section>

      {/* 角色能力边界 */}
      <section className="mb-6">
        <h2 className="mb-2.5 text-[13px] font-medium text-cool-ink">角色能力边界</h2>
        <div className="grid grid-cols-1 gap-2.5 md:grid-cols-2 xl:grid-cols-4">
          {CAPABILITIES.map((group) => {
            const current = group.role === role
            return (
              <div
                key={group.role}
                className={`rounded-xl border bg-cool-surface p-3.5 shadow-console ${
                  current ? 'border-steel/45' : 'border-cool-line'
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[12.5px] font-medium text-cool-ink">{ROLE_LABEL[group.role]}</span>
                  {current && (
                    <span className="rounded-full border border-steel/45 bg-steel/10 px-2 py-0.5 text-[10.5px] text-steel-deep">
                      当前
                    </span>
                  )}
                </div>
                <ul className="mt-2 space-y-1.5">
                  {group.items.map((item) => (
                    <li key={item} className="flex gap-1.5 text-[11.5px] leading-relaxed text-cool-ink-3">
                      <span className="text-cool-ink-4">·</span>
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )
          })}
        </div>
      </section>

      {/* 接口鉴权实况 */}
      <section className="mb-6">
        <h2 className="mb-2.5 text-[13px] font-medium text-cool-ink">接口鉴权实况</h2>
        <div className="overflow-hidden rounded-xl border border-cool-line bg-cool-surface shadow-console">
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-[12.5px]">
              <thead>
                <tr className="bg-cool-surface-2 text-left text-cool-ink-3">
                  <th className="px-3.5 py-2.5 font-medium">接口</th>
                  <th className="px-3.5 py-2.5 font-medium">最低角色</th>
                  <th className="px-3.5 py-2.5 font-medium">状态</th>
                </tr>
              </thead>
              <tbody>
                {GUARDED.map((item) => {
                  const allowed = (ROLE_ORDER[role] ?? -1) >= (ROLE_ORDER[item.min] ?? 99)
                  return (
                    <tr key={item.path} className="border-t border-cool-line">
                      <td className="px-3.5 py-2.5 font-mono text-[11.5px] text-cool-ink-2">{item.path}</td>
                      <td className="px-3.5 py-2.5 text-cool-ink-2">{ROLE_LABEL[item.min]}</td>
                      <td className="px-3.5 py-2.5">
                        <span className={`rounded-full border px-2 py-0.5 text-[10.5px] ${allowed ? TONE_CLASS.ok : TONE_CLASS.idle}`}>
                          {allowed ? '可调用' : '将返回 403'}
                        </span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <div className="border-t border-cool-line bg-cool-surface-2 px-3.5 py-2.5 text-[11.5px] text-cool-ink-3">
            其余接口（检索、问答、数字人、感知、行程、创作、目的地与景区）为公开接口，未挂 RBAC 依赖，游客端未登录即可调用。
          </div>
        </div>
      </section>

      {/* 如实说明 */}
      <section>
        <h2 className="mb-2.5 text-[13px] font-medium text-cool-ink">当前实现的边界</h2>
        <div className="flex flex-col gap-2.5">
          <Boundary tone="warn" title="账号体系为内置账号，尚无用户表">
            后端 <code>core/security.py</code> 的 <code>authenticate()</code> 校验的是环境变量
            <code> ADMIN_USERNAME</code> / <code>ADMIN_PASSWORD</code>，登录即授予管理员等级。
            因此本页没有可列出的用户清单。生产需落数据库用户表（含商户子账号与租户隔离），
            属 docs/09 §7 登记的后续工作。
          </Boundary>
          <Boundary tone="warn" title="专家等级已定义但未启用">
            <code>ROLE_EXPERT</code> 在 <code>ROLE_ORDER</code> 中存在（等级 2），但全项目没有任何
            守卫使用它。这意味着当前「专家」与「运营」的实际权限**完全相同**，
            内容审核的等级门槛尚未收紧。
          </Boundary>
          <Boundary tone="ok" title="前端守卫只是体验层">
            未登录时前端会拦在 <code>/admin/login</code>，但这不构成安全边界。
            真正的鉴权在每个受保护接口上（<code>require_editor</code>），绕过前端直接请求仍会被拒。
          </Boundary>
        </div>
      </section>
    </div>
  )
}

function Boundary({ tone, title, children }: { tone: 'ok' | 'warn'; title: string; children: React.ReactNode }) {
  const skin =
    tone === 'ok'
      ? 'border-steel/35 bg-steel/10'
      : 'border-amber/40 bg-amber/10'
  return (
    <div className={`rounded-xl border px-3.5 py-3 ${skin}`}>
      <div className="text-[12.5px] font-medium text-cool-ink">{title}</div>
      <p className="mt-1 text-[11.5px] leading-relaxed text-cool-ink-2">{children}</p>
    </div>
  )
}
