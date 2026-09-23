/**
 * 工单19 §4 · 多模态内容输出与分享（分享落地页）
 * 工单16-20 延伸 · 平台化双端重构（批次 0）：迁入 ToC 路由 /s/:token。
 *
 * 兼容性：旧分享链接形如 `/?share=<token>`（工单19 原实现，前端当时无路由库）。
 * 这里同时接受路由参数与查询参数，老链接无需重发即可打开。
 */
import { useParams } from 'react-router-dom'
import { SharedContentView } from '../../../components/SharePanel'

export default function ShareLandingPage() {
  const params = useParams<{ token: string }>()
  const legacy = new URLSearchParams(window.location.search).get('share')
  const token = params.token ?? legacy ?? ''

  return <SharedContentView token={token} onExit={() => window.history.back()} />
}
