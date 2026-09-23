/**
 * 工单16-20 延伸 · 平台化双端重构（批次 0）
 * 双端路由装配的渲染测试。
 *
 * 为什么需要它：HTTP 200 只能证明 vite 的 SPA 回落可用，证明不了 React Router
 * 真的渲染出了对应页面。而 index 路由的写法（不得同时带 path）是装配环节最易出错、
 * 且只能靠真实渲染才能发现的地方。
 *
 * App 内部使用 BrowserRouter，故这里通过 jsdom 的 history API 改地址后整体渲染。
 */
import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { clearSession, saveSession } from '../shared/utils/auth'

// 数字人舞台需要 WebGL，jsdom 不提供，故在路由测试中替换为占位组件。
// 这里要验证的是「路由 + 布局壳 + 页面组装」是否正确，3D 渲染本身由浏览器验证。
// 断言占位组件确实被渲染，即可证明 GuidePage 仍把 AvatarStage 组装在页面里。
vi.mock('../components/AvatarStage', () => ({
  default: () => <div data-testid="avatar-stage" />,
}))

import App from '../App'

const goto = (path: string) => {
  window.history.pushState({}, '', path)
  return render(<App />)
}

/**
 * 已登录地进入 ToB 路由。
 * 批次 4 给 /admin/* 加了 RequireAuth，未种令牌时会被重定向到登录页，
 * 因此凡是要断言控制台内部渲染的用例都必须先建会话
 * （登录页自身的用例才用裸 goto）。
 */
const gotoAuthed = (path: string) => {
  saveSession('test-token', 'admin', 'tester')
  return goto(path)
}

beforeEach(() => {
  // 控制台总览会真实请求 /readyz 与 /stack，这里按后端实机形状打桩，
  // 顺便覆盖「redis 探活失败」这一关键路径的渲染。
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      // 按端点分流：目的地的 items 是数组、景区详情的 items 不存在，
      // 若不分流，新页面会拿到 readyz 的形状而在 .map 上崩掉
      let data: unknown
      if (url.includes('/destination')) {
        data = {
          items: [
            { id: 'd1', name: '杭州', region: '浙江·杭州', summary: '湖山与人文叠印', description: '', tags: ['江南'], park_count: 2 },
            { id: 'd2', name: '苏州', region: '江苏·苏州', summary: '园林之城', description: '', tags: ['园林'], park_count: 2 },
          ],
          total: 2,
        }
      } else if (url.includes('/park/')) {
        data = {
          id: 'p1',
          name: '拙政园',
          destination_id: 'd2',
          destination_name: '苏州',
          summary: '江南园林之首',
          description: '全园以水景为核心。',
          open_hours: '07:30-17:30',
          status: 'open',
          daily_capacity: 12000,
          level: '5A',
          ticket_notice: '旺季需按预约时段入园。',
          cover_uri: null,
          tags: ['世界遗产', '园林'],
          attraction_count: 1,
          distance_m: null,
          destination: { id: 'd2', name: '苏州', region: '江苏·苏州' },
          attractions: [
            { id: 'a1', name: '远香堂', summary: '全园主厅', description: '', open_hours: '07:30-17:30', tags: ['厅堂'], park_id: 'p1' },
          ],
          activities: [],
        }
      } else if (url.includes('/park')) {
        data = {
          items: [
            {
              id: 'p1',
              name: '拙政园',
              destination_id: 'd2',
              destination_name: '苏州',
              summary: '江南园林之首',
              description: '',
              open_hours: '07:30-17:30',
              status: 'open',
              daily_capacity: 12000,
              level: '5A',
              ticket_notice: '',
              cover_uri: null,
              tags: ['世界遗产', '园林'],
              attraction_count: 3,
              distance_m: null,
            },
            {
              id: 'p2',
              name: '灵隐飞来峰',
              destination_id: 'd1',
              destination_name: '杭州',
              summary: '石窟造像群',
              description: '',
              open_hours: '07:00-18:00',
              status: 'maintenance',
              daily_capacity: 20000,
              level: '4A',
              ticket_notice: '',
              cover_uri: null,
              tags: ['石刻'],
              attraction_count: 3,
              distance_m: 1200,
            },
          ],
          total: 2,
          has_geo: false,
        }
      } else if (url.includes('/create/assets')) {
        // SharePanel 挂载即拉作品列表；返回空列表而不是 readyz 形状，否则 items.map 会崩
        data = { items: [], total: 0 }
      } else if (url.includes('/audit/compliance')) {
        data = {
          checks: [
            { item: '身份与权限', status: 'ok', detail: 'OAuth2 + JWT + RBAC' },
            { item: '传输加密', status: 'pending', detail: '开发环境为 HTTP' },
          ],
          pending: 1,
        }
      } else if (url.includes('/audit/logs')) {
        data = {
          items: [
            {
              id: 'log1',
              method: 'POST',
              path: '/api/v1/kb/ingest',
              status: 200,
              client_ip: '127.0.***.***',
              role: 'admin',
              trace_id: 'abcdef1234567890',
              created_at: '2026-09-22T10:00:00',
            },
          ],
          total: 1,
        }
      } else if (url.includes('/kb')) {
        data = {
          items: [
            { id: 'k1', title: '五亭桥', content: '五亭桥又名莲花桥。', modality: 'text', media_uri: '', tags: ['清代'], source: '景区志' },
            { id: 'k2', title: '白塔', content: '白塔立于湖畔。', modality: 'image', media_uri: 'minio://x', tags: [], source: '景区志' },
          ],
          total: 2,
          limit: 20,
          offset: 0,
        }
      } else if (url.includes('/stack')) {
        data = { llm_mode: 'cloud', llm: 'Qwen/Qwen2.5-72B', embedding_model: 'BAAI/bge-m3' }
      } else {
        data = {
          work_order: '人工智能CV-AIGC-17',
          services: {
            database: { ok: true, postgis: '3.4.0' },
            redis: { ok: false, error: 'ConnectionRefusedError: boom' },
            milvus: { ok: true, collections: ['wenlv_chunks'] },
          },
        }
      }
      return new Response(JSON.stringify({ code: 0, message: 'ok', data, trace_id: 'test' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }),
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
  // 登录态存在 sessionStorage 里，不清会串到下一个用例，令"未登录"用例假通过
  clearSession()
  window.history.pushState({}, '', '/')
})

describe('双端路由装配', () => {
  it('ToC 根路径渲染游客端布局壳与首页', () => {
    goto('/')
    expect(screen.getByText('文旅创新智脑')).toBeInTheDocument()
    expect(screen.getByText('通用文旅数字人导览与内容共创')).toBeInTheDocument()
  })

  it('导览页仍组装数字人舞台与状态区（现有能力已完成迁移）', async () => {
    goto('/guide')
    // 占位组件被渲染 => GuidePage 仍把 AvatarStage 组装在页面里
    expect(screen.getByTestId('avatar-stage')).toBeInTheDocument()
    // 以下两处来自原 App.tsx 的状态区，迁移后不应丢失
    expect(screen.getByText('青瓷')).toBeInTheDocument()
    expect(screen.getByText(/情绪 ·/)).toBeInTheDocument()
    // 技术栈信息条原先在页头，页头改由 TocShell 提供后移入页内 —— 等 /stack 落地，
    // 既验证信息条仍在，也让 GuidePage 的初始请求结束、避免 act 警告
    expect(await screen.findByText('LLM Qwen/Qwen2.5-72B')).toBeInTheDocument()
  })

  it('ToB 路径渲染运营控制台布局壳（冷色壳，含侧栏分组）', async () => {
    gotoAuthed('/admin')
    // 先等总览页的异步请求落地，避免未包裹 act 的状态更新警告
    expect(await screen.findByText('database')).toBeInTheDocument()
    expect(screen.getByText('运营控制台')).toBeInTheDocument()
    expect(screen.getByText('景区运营 · 管理端')).toBeInTheDocument()
    // 侧栏分组名来自 tobNavGroups
    expect(screen.getAllByText('内容').length).toBeGreaterThan(0)
    expect(screen.getAllByText('治理').length).toBeGreaterThan(0)
  })

  it('未实现模块渲染建设中提示，并如实标注工单依据与场景号', () => {
    // 批次 4 后 ToB 已落地 6 条，改用仍未实现的数据查询验证同一条装配逻辑
    // （需带登录态：未实现的页面同样在 RequireAuth 之后）
    gotoAuthed('/admin/query')
    expect(screen.getByText('数据查询建设中')).toBeInTheDocument()
    expect(screen.getByText(/工单17 §2.2/)).toBeInTheDocument()
    expect(screen.getByText(/场景 · S8/)).toBeInTheDocument()
  })

  it('未知路径重定向回首页', () => {
    goto('/no-such-page')
    expect(screen.getByText('通用文旅数字人导览与内容共创')).toBeInTheDocument()
  })
})

describe('控制台总览（对 /readyz 实机形状）', () => {
  it('下钻到 services，逐组件显示状态而非塌成一行', async () => {
    gotoAuthed('/admin')
    // 三个组件名必须各自出现 —— 若只摊平顶层，这里只会有一个 services
    expect(await screen.findByText('database')).toBeInTheDocument()
    expect(screen.getByText('redis')).toBeInTheDocument()
    expect(screen.getByText('milvus')).toBeInTheDocument()
    expect(screen.queryByText('services')).not.toBeInTheDocument()
  })

  it('探活失败显示「异常」而非绿色「正常」，并露出失败原因', async () => {
    gotoAuthed('/admin')
    // redis 是 { ok: false, error: … }：不得被判为正常
    expect(await screen.findByText('异常')).toBeInTheDocument()
    expect(screen.getByText(/ConnectionRefusedError/)).toBeInTheDocument()
    // database/milvus 为 ok: true
    expect(screen.getAllByText('正常').length).toBeGreaterThanOrEqual(2)
  })

  it('成功项展示有信息量的字段（postgis 版本 / 集合名）', async () => {
    gotoAuthed('/admin')
    expect(await screen.findByText('3.4.0')).toBeInTheDocument()
    expect(screen.getByText('wenlv_chunks')).toBeInTheDocument()
  })
})

describe('批次 1 · 通用化页面（docs/09 G1）', () => {
  it('发现页渲染目的地与景区卡片，并显示营业状态标签', async () => {
    goto('/explore')
    // 「杭州」既是目的地名、也是景区的所属目的地，故用 findAll 避免多匹配报错
    expect((await screen.findAllByText('杭州')).length).toBeGreaterThan(0)
    expect((await screen.findAllByText('拙政园')).length).toBeGreaterThan(0)
    // 状态标签由 PARK_STATUS 映射得出，而不是直接显示后端字段值
    expect(screen.getByText('营业中')).toBeInTheDocument()
    expect(screen.getByText('维护中')).toBeInTheDocument()
  })

  it('景区详情页渲染所属目的地、景点与票务须知', async () => {
    goto('/park/p1')
    expect((await screen.findAllByText('拙政园')).length).toBeGreaterThan(0)
    expect(screen.getByText('远香堂')).toBeInTheDocument()
    expect(screen.getByText('旺季需按预约时段入园。')).toBeInTheDocument()
    expect(screen.getByText(/江苏·苏州/)).toBeInTheDocument()
  })

  it('管理端景区台账渲染指标条与表格', async () => {
    gotoAuthed('/admin/parks')
    expect(await screen.findByText('景区总数')).toBeInTheDocument()
    expect(screen.getByText('景点总数')).toBeInTheDocument()
    // 「景区与景点管理」在侧栏导航与本页标题各出现一次
    expect(screen.getAllByText('景区与景点管理').length).toBeGreaterThanOrEqual(2)
    expect((await screen.findAllByText('灵隐飞来峰')).length).toBeGreaterThan(0)
  })
})

describe('批次 2 · 问答与创作页面化（工单17 §1 / 工单19）', () => {
  it('问答页渲染三种输入入口与空态引导', async () => {
    goto('/ask')
    expect(await screen.findByText('多模态问答')).toBeInTheDocument()
    expect(screen.getByText('拍照 / 传图')).toBeInTheDocument()
    // 语音输入是批次 2 补齐的能力；jsdom 无 MediaRecorder，应降级为明确提示而不是静默失败
    expect(screen.getByText('当前浏览器不支持录音，请改用文字或图片提问')).toBeInTheDocument()
    expect(screen.getByText('还没有提问')).toBeInTheDocument()
  })

  it('创作页聚焦纪念内容并已从导览页拆出', async () => {
    goto('/create')
    expect(await screen.findByText('纪念内容创作')).toBeInTheDocument()
  })

  it('导览页不再承载内容创作工作台', async () => {
    goto('/guide')
    expect(screen.getByTestId('avatar-stage')).toBeInTheDocument()
    expect(screen.queryByText('创意策划与内容生成')).not.toBeInTheDocument()
  })
})

describe('批次 3 · 行程/活动/地图/我的（工单19 / 工单20 场景13）', () => {
  it('行程页渲染策划入口', async () => {
    goto('/plan')
    expect(await screen.findByText('个性化行程策划')).toBeInTheDocument()
  })

  it('活动页渲染推荐入口', async () => {
    goto('/activity')
    expect(await screen.findByText('活动与体验')).toBeInTheDocument()
  })

  it('地图页在无产出时给出可操作的引导而不是空白', async () => {
    goto('/map')
    expect(await screen.findByText('导览地图')).toBeInTheDocument()
    expect(await screen.findByText(/还没有导览地图/)).toBeInTheDocument()
    expect(screen.getByText('去生成')).toBeInTheDocument()
  })

  it('我的页渲染作品与分享，并如实标注订单属后续批次', async () => {
    goto('/me')
    // 「我的」同时出现在底部 Tab 与本页标题，故用 findAll
    expect(await screen.findAllByText('我的')).not.toHaveLength(0)
    expect(screen.getByText('订单与电子票')).toBeInTheDocument()
    expect(screen.getByText(/属批次 5/)).toBeInTheDocument()
  })
})
