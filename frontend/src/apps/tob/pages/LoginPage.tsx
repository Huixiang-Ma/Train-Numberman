/**
 * 工单16 §5 · 运营端登录（批次 4）
 *
 * 唯一免鉴权页面，因此**不套 TobShell**（见 shared/components/RequireAuth.tsx 的说明）。
 * 视觉仍是冷色体系：登录页属于控制台的入口，用暖色会让两端气质在入口处就串了。
 */
import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { api } from '../../../api/client'
import { ROLE_LABEL, saveSession } from '../../../shared/utils/auth'

export default function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const from = (location.state as { from?: string } | null)?.from ?? '/admin'

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    try {
      const result = await api.login(username.trim(), password)
      saveSession(result.access_token, result.role, username.trim())
      navigate(from, { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid min-h-screen place-items-center bg-cool-bg px-4 font-ui text-cool-ink">
      <div className="w-full max-w-[380px]">
        <div className="mb-5 flex items-center gap-2.5">
          <span className="grid h-9 w-9 place-items-center rounded-lg bg-steel text-[16px] font-semibold text-white">
            运
          </span>
          <div className="leading-tight">
            <div className="text-[15px] font-semibold">运营控制台</div>
            <div className="text-[11.5px] text-cool-ink-3">文旅创新智脑 · 景区运营端</div>
          </div>
        </div>

        <form
          onSubmit={submit}
          className="rounded-xl border border-cool-line bg-cool-surface p-5 shadow-console"
        >
          <label className="block">
            <span className="text-[12px] text-cool-ink-3">账号</span>
            <input
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
              className="mt-1.5 w-full rounded-lg border border-cool-line bg-cool-bg px-3 py-2.5 text-[13px] text-cool-ink outline-none placeholder:text-cool-ink-4 focus:border-steel/50"
              placeholder="管理员账号"
            />
          </label>

          <label className="mt-3.5 block">
            <span className="text-[12px] text-cool-ink-3">密码</span>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              className="mt-1.5 w-full rounded-lg border border-cool-line bg-cool-bg px-3 py-2.5 text-[13px] text-cool-ink outline-none placeholder:text-cool-ink-4 focus:border-steel/50"
              placeholder="••••••••"
            />
          </label>

          {error && (
            <div className="mt-3.5 rounded-lg border border-clay/45 bg-clay/12 px-3 py-2 text-[12.5px] text-clay-deep">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={busy || !username || !password}
            className="mt-4 w-full rounded-lg bg-steel py-2.5 text-[13px] font-medium text-white transition disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? '登录中…' : '登录'}
          </button>

          <p className="mt-3.5 text-[11.5px] leading-relaxed text-cool-ink-4">
            账号由后端环境变量 <code className="text-cool-ink-3">ADMIN_USERNAME</code> /{' '}
            <code className="text-cool-ink-3">ADMIN_PASSWORD</code> 配置，登录后获得
            <span className="text-cool-ink-3">{ROLE_LABEL.admin}</span>权限。
            知识库与审计接口要求运营及以上角色，未登录时前端会拦在本页。
          </p>
        </form>

        <button
          onClick={() => navigate('/')}
          className="mt-4 w-full rounded-lg border border-cool-line bg-cool-surface py-2 text-[12.5px] text-cool-ink-3 hover:border-steel/40 hover:text-steel-deep"
        >
          返回游客端
        </button>
      </div>
    </div>
  )
}
