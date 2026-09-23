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
      // 桩的分支顺序必须**由具体到宽泛**，否则宽泛的分支会先命中：
      //   · `/analytics/datasets` 含 "dataset"，须先于 `/analytics/dataset/`
      //   · `/ticket/park/xxx` 含 "/park/"，须先于景区详情用的 `/park/`
      // 顺序反了页面会拿到错误形状并崩在 .map / .tickets 上。
      if (url.includes('/analytics/datasets')) {
        data = {
          items: [
            { name: 'parks', label: '景区台账' },
            { name: 'orders', label: '票务订单' },
            { name: 'queries', label: '游客提问' },
          ],
          total: 3,
        }
      } else if (url.includes('/analytics/dataset/')) {
        data = {
          name: 'parks',
          label: '景区台账',
          columns: ['名称', '等级', '状态'],
          rows: [
            ['拙政园', '5A', 'open'],
            ['灵隐飞来峰', '4A', 'maintenance'],
          ],
        }
      } else if (url.includes('/analytics/parks')) {
        data = {
          items: [
            {
              park_id: 'p1',
              park_name: '拙政园',
              level: '5A',
              status: 'open',
              daily_capacity: 12000,
              ticket_types: 4,
              orders: 6,
              orders_pending: 1,
              tickets: 4,
              amount_cents: 40000,
              orders_checked_in: 1,
              checkin_rate: 0.5,
              reviews: 1,
              rating: 4.0,
              service_open: 0,
            },
          ],
          total: 1,
        }
      } else if (url.includes('/analytics/business')) {
        data = {
          park_id: null,
          days: 30,
          ticket: {
            orders_total: 6,
            orders_pending: 1,
            orders_paid: 2,
            orders_checked_in: 1,
            orders_refunded: 1,
            tickets_sold: 4,
            tickets_checked_in: 2,
            amount_cents: 40000,
            checkin_rate: 0.5,
          },
          ticket_structure: [{ name: '成人票', category: 'adult', quantity: 4, amount_cents: 40000, share: 1 }],
          checkin_hours: [{ hour: 10, count: 2 }],
          order_trend: [
            { date: '2026-09-22', orders: 2, tickets: 3 },
            { date: '2026-09-23', orders: 4, tickets: 1 },
          ],
          content: { by_kind: [{ kind: 'image', count: 88 }], total: 88, share_links: 3, share_visits: 7 },
          review: { total: 1, average: 4.0, distribution: { '5': 0, '4': 1, '3': 0, '2': 0, '1': 0 } },
          service: {
            total: 2,
            open: 1,
            urgent_open: 1,
            resolved: 1,
            by_category: { consult: 1, complaint: 0, lost: 0, help: 1 },
            resolve_rate: 0.5,
            avg_response_minutes: 0.1,
          },
          gaps: [
            { item: '闸口物理客流', reason: '闸机未接入' },
            { item: '票务收入对账', reason: '支付为占位实现' },
          ],
        }
      } else if (url.includes('/analytics/insight')) {
        data = {
          days: 30,
          total: 8,
          recent: 8,
          multimodal: 2,
          multimodal_ratio: 0.25,
          avg_latency_ms: 1234,
          intents: [
            { intent: 'qa', label: '知识问答', count: 5, share: 0.625 },
            { intent: 'activity', label: '活动推荐', count: 3, share: 0.375 },
          ],
          sources: [{ source: 'query', count: 6 }],
          trend: [
            { date: '2026-09-22', count: 3 },
            { date: '2026-09-23', count: 5 },
          ],
          hot_words: [
            { word: '五亭', count: 4 },
            { word: '亭桥', count: 4 },
            { word: '讲解', count: 2 },
          ],
          hot_word_method: '中文二元组词频（未引入分词器）',
          park_mentions: [{ park_name: '平江历史街区', count: 1 }],
          park_mention_method: '景区名在问题文本中的字符串命中，非语义归属',
          blind_spots: [{ question: '这个景区适合带孩子玩吗', intent: 'qa', created_at: '2026-09-23T10:00:00' }],
          recent_questions: [
            {
              question: '五亭桥为什么叫五亭桥',
              intent: 'qa',
              intent_label: '知识问答',
              citations: 3,
              source: 'query',
              has_image: false,
              has_audio: false,
              created_at: '2026-09-23T10:00:00',
            },
          ],
          gaps: [{ item: '问题语义聚类', reason: '未引入分词与向量聚类组件' }],
        }
      } else if (url.includes('/ticket/admin/stats')) {
        data = {
          orders_total: 6,
          orders_pending: 1,
          orders_paid: 2,
          orders_checked_in: 1,
          orders_refunded: 1,
          tickets_sold: 4,
          tickets_checked_in: 2,
          amount_cents: 40000,
          checkin_rate: 0.5,
        }
      } else if (url.includes('/ticket/admin/orders')) {
        data = { items: [], total: 0 }
      } else if (url.includes('/ticket/park/')) {
        data = {
          park: { id: 'p1', name: '拙政园', level: '5A', ticket_notice: '旺季需按预约时段入园。' },
          ticket_types: [
            {
              id: 'tt1',
              park_id: 'p1',
              name: '成人票',
              category: 'adult',
              price_cents: 10000,
              price: 100,
              currency: 'CNY',
              refundable: true,
              valid_days: 1,
              notice: '5A 景区全园通票，当日一次有效。',
              status: 'on_sale',
              slots: [
                {
                  id: 's1',
                  ticket_type_id: 'tt1',
                  slot_date: '2026-09-23',
                  start_time: '08:00',
                  end_time: '11:00',
                  inventory: 1000,
                  sold: 2,
                  remaining: 998,
                  sold_out: false,
                },
              ],
            },
            {
              id: 'tt2',
              park_id: 'p1',
              name: '学生票',
              category: 'student',
              price_cents: 5000,
              price: 50,
              currency: 'CNY',
              refundable: true,
              valid_days: 1,
              notice: '',
              status: 'on_sale',
              slots: [],
            },
          ],
          days: 7,
        }
      } else if (url.includes('/ticket/orders') || url.includes('/ticket/slots/')) {
        data = { items: [], total: 0 }
      } else if (url.includes('/ticket/slot/')) {
        // 注意与 /ticket/slots/ 的区分：前者末尾是 "/"，后者是 "s/"，
        // 因此判断顺序必须先 slots 后 slot，否则 slot 分支永远命中不到。
        data = {
          park: { id: 'p1', name: '拙政园', level: '5A' },
          ticket_type: {
            id: 'tt1',
            park_id: 'p1',
            name: '成人票',
            category: 'adult',
            price_cents: 10000,
            price: 100,
            currency: 'CNY',
            refundable: true,
            valid_days: 1,
            notice: '',
            status: 'on_sale',
          },
          slot: {
            id: 's1',
            ticket_type_id: 'tt1',
            slot_date: '2026-09-23',
            start_time: '08:00',
            end_time: '11:00',
            inventory: 1000,
            sold: 2,
            remaining: 998,
            sold_out: false,
          },
        }
      } else if (url.includes('/service/admin/stats')) {
        data = {
          total: 2,
          open: 1,
          urgent_open: 1,
          resolved: 1,
          by_category: { consult: 1, complaint: 0, lost: 0, help: 1 },
          resolve_rate: 0.5,
          avg_response_minutes: 0.1,
        }
      } else if (url.includes('/service/admin/requests') || url.includes('/service/my')) {
        data = { items: [], total: 0 }
      } else if (url.includes('/review/park/')) {
        data = { items: [], total: 0, summary: { total: 0, average: 0, distribution: { '5': 0, '4': 0, '3': 0, '2': 0, '1': 0 } } }
      } else if (url.includes('/destination')) {
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

  it('视觉识别反馈内嵌数字人舞台，不再有独立的感知结果面板', () => {
    goto('/guide')
    // 交互层与采集控件都收进舞台这一侧
    expect(screen.getByText('视觉感知已嵌入数字人')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '开启摄像头' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '上传图像感知' })).toBeInTheDocument()
    // 独立面板的标题必须消失：识别内容改由数字人本体表达
    expect(screen.queryByText('感知结果')).not.toBeInTheDocument()
    expect(screen.queryByText('实时行为感知')).not.toBeInTheDocument()
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

  it('控制台内的未知路径给出兜底页，而不是只有侧栏的空白页', async () => {
    // 批次 6 后全部路由都已实现，原先用来验证"建设中"的用例失去了目标；
    // 这里改为验证控制台内未注册路径的兜底 —— 缺了它，/admin/typo 会渲染出
    // 只有侧栏、内容空白的页面，现场会以为系统坏了。
    gotoAuthed('/admin/typo-not-registered')
    expect(await screen.findByText('控制台页面不存在')).toBeInTheDocument()
    expect(screen.getByText('运营控制台')).toBeInTheDocument()
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

  it('我的页渲染作品、票务概览与反馈入口', async () => {
    goto('/me')
    // 「我的」同时出现在底部 Tab 与本页标题，故用 findAll
    expect(await screen.findAllByText('我的')).not.toHaveLength(0)
    // 批次 5 完成后，订单已可用：原先"属批次 5、尚未开放"的占位说明必须消失，
    // 否则界面会自我否定。这条断言就是防止它回潮。
    expect(await screen.findByText('订单与电子票')).toBeInTheDocument()
    expect(screen.queryByText(/尚未开放/)).not.toBeInTheDocument()
    expect(screen.getByText('查看全部订单')).toBeInTheDocument()
    expect(screen.getByText('去提交 / 查看')).toBeInTheDocument()
  })
})

describe('批次 4 · 运营控制台（工单16 §5 / 工单17 §2.2 / §5）', () => {
  it('未登录访问控制台被拦到登录页，且登录页不在控制台壳内', () => {
    goto('/admin')
    // 登录页独有文案
    expect(screen.getByText('文旅创新智脑 · 景区运营端')).toBeInTheDocument()
    // 关键：登录页不得渲染在 TobShell 之内，否则侧栏/顶栏会一起出现
    expect(screen.queryByText('景区运营 · 管理端')).not.toBeInTheDocument()
  })

  it('已登录后可进入控制台，顶栏与侧栏分组正常', async () => {
    gotoAuthed('/admin')
    expect(await screen.findByText('database')).toBeInTheDocument()
    expect(screen.getByText('景区运营 · 管理端')).toBeInTheDocument()
  })

  it('知识库页渲染条目、模态中文标签与分页', async () => {
    gotoAuthed('/admin/kb')
    expect(await screen.findByText('五亭桥')).toBeInTheDocument()
    expect(screen.getByText('白塔')).toBeInTheDocument()
    // 模态经 KB_MODALITY 映射为中文（筛选下拉里也有同名 option，故用 getAll）
    expect(screen.getAllByText('文本').length).toBeGreaterThan(0)
    expect(screen.getAllByText('图像').length).toBeGreaterThan(0)
    expect(screen.getByText(/共 2 条/)).toBeInTheDocument()
  })

  it('审核页渲染合规自查与审计日志，未落实项如实标注', async () => {
    gotoAuthed('/admin/review')
    expect(await screen.findByText('身份与权限')).toBeInTheDocument()
    expect(screen.getByText(/1 项待落实/)).toBeInTheDocument()
    expect(screen.getAllByText('待落实').length).toBeGreaterThan(0)
    expect(await screen.findByText('/api/v1/kb/ingest')).toBeInTheDocument()
  })

  it('权限页回显当前账号与角色，并如实标出专家等级未启用', () => {
    gotoAuthed('/admin/users')
    // 「用户与权限」在侧栏与本页标题各出现一次
    expect(screen.getAllByText('用户与权限').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText('tester')).toBeInTheDocument()
    expect(screen.getAllByText('管理员').length).toBeGreaterThan(0)
    // 这是权限页最重要的一条如实说明，不能被粉饰掉
    expect(screen.getByText(/全项目没有任何/)).toBeInTheDocument()
  })
})

describe('批次 5 · 票务与游客服务（docs/09 G3/G4）', () => {
  it('票务大厅列出景区、起价与今日余票', async () => {
    goto('/tickets')
    expect(await screen.findByText('门票预订')).toBeInTheDocument()
    expect((await screen.findAllByText('拙政园')).length).toBeGreaterThan(0)
    // 起价取"在售票种"最低值：成人 100 元 / 学生 50 元 → 50 元起。
    // 用 getAll：票种 chip 上也会出现同一个 ¥50.00，getBy 会因多匹配而报错
    expect(screen.getAllByText(/¥50\.00/).length).toBeGreaterThan(0)
    // 桩数据有 2 个景区，每个各出一个入口 —— 用 getAll 顺带验证"大厅列出多个景区"
    expect(screen.getAllByText('选择场次购票').length).toBeGreaterThanOrEqual(2)
  })

  it('购票页渲染票种、时段、余票与底部结算条', async () => {
    goto('/tickets/p1')
    expect(await screen.findByText('拙政园 · 门票预订')).toBeInTheDocument()
    // 购票须知来自景区档案
    expect(screen.getByText('旺季需按预约时段入园。')).toBeInTheDocument()
    expect(screen.getByText('成人票')).toBeInTheDocument()
    expect(screen.getByText('学生票')).toBeInTheDocument()
    expect(screen.getByText('08:00–11:00')).toBeInTheDocument()
    expect(screen.getByText('余票 998')).toBeInTheDocument()
    // 结算条给出总价与下单入口
    expect(screen.getByText('确认下单')).toBeInTheDocument()
    // 「一单一票」这条必须说明，否则游客会以为整单只需核销一次
    expect(screen.getByText(/各自核销/)).toBeInTheDocument()
  })

  it('下单深链由时段 id 还原出景区与场次', async () => {
    goto('/booking/s1')
    expect(await screen.findByText('为你锁定这一场')).toBeInTheDocument()
    expect(screen.getByText(/拙政园 · 成人票/)).toBeInTheDocument()
    expect(screen.getByText('查看其他场次')).toBeInTheDocument()
  })

  it('我的订单在无订单时给出可操作引导而不是空白', async () => {
    goto('/me/orders')
    expect(await screen.findByText('我的订单')).toBeInTheDocument()
    expect(await screen.findByText(/还没有订单/)).toBeInTheDocument()
  })

  it('反馈页给出四类服务入口，并在紧急求助时提示线下渠道', async () => {
    goto('/feedback')
    expect(await screen.findByText('评价与反馈')).toBeInTheDocument()
    for (const label of ['咨询', '投诉建议', '失物招领', '紧急求助']) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0)
    }
    // 默认不是紧急求助，不应出现线下提示；点了才出现
    expect(screen.queryByText(/同时联系现场工作人员/)).not.toBeInTheDocument()
  })

  it('核销台渲染闸口、票号输入与「不可重复入园」的职责说明', async () => {
    gotoAuthed('/admin/checkin')
    expect(await screen.findByText('电子票核销台')).toBeInTheDocument()
    expect(screen.getByText('闸口')).toBeInTheDocument()
    expect(screen.getByText('票号 / 二维码内容')).toBeInTheDocument()
    expect(screen.getByText('核 销')).toBeInTheDocument()
    // 未核销前不应出现任何结果横幅
    expect(screen.queryByText('核销成功，请放行')).not.toBeInTheDocument()
  })

  it('票种与库存页按景区展示票种并给出库存下限', async () => {
    gotoAuthed('/admin/tickets')
    expect(await screen.findByText('票种与时段库存')).toBeInTheDocument()
    expect(await screen.findByText('成人票')).toBeInTheDocument()
    // 总量 1000 / 已售 2 → 余票 998，与购票页口径一致
    expect(screen.getAllByText(/余票/).length).toBeGreaterThan(0)
    expect(screen.getByText('新建票种')).toBeInTheDocument()
  })

  it('订单管理页的核销率注明分母口径', async () => {
    gotoAuthed('/admin/orders')
    // 「订单管理」在侧栏与本页标题各出现一次
    expect((await screen.findAllByText('订单管理')).length).toBeGreaterThanOrEqual(2)
    expect(await screen.findByText('核销率')).toBeInTheDocument()
    // 分母口径必须写在界面上，否则运营会拿它跟"总订单数"对比而误判
    expect(screen.getByText(/不含待支付/)).toBeInTheDocument()
    expect(screen.getByText('¥400.00')).toBeInTheDocument()
  })

  it('游客服务工单页区分加急与普通咨询', async () => {
    gotoAuthed('/admin/service')
    // 同样在侧栏与标题各出现一次
    expect((await screen.findAllByText('游客服务工单')).length).toBeGreaterThanOrEqual(2)
    expect(await screen.findByText('加急待处理')).toBeInTheDocument()
    // 排序由后端决定，前端不应再排一次
    expect(screen.getByText(/顺序由后端按紧急度排定/)).toBeInTheDocument()
  })
})

describe('批次 6 · 数据分析与快捷指令（docs/09 G5 / 工单16 S8·S9）', () => {
  it('经营分析页渲染票务 KPI、核销时段与跨景区对比', async () => {
    gotoAuthed('/admin/analytics')
    expect(await screen.findByText('票务')).toBeInTheDocument()
    expect(screen.getByText('票种销售结构')).toBeInTheDocument()
    expect(screen.getByText('核销时段分布')).toBeInTheDocument()
    expect(screen.getByText('跨景区对比（近 30 天）')).toBeInTheDocument()
    // 入园时段是代理指标这件事必须写出来，否则会被当成真实客流用于汇报
    expect(screen.getByText(/不等于真实客流/)).toBeInTheDocument()
    // 核销率的分母口径同样要写在页面上
    expect(screen.getByText(/不含待支付/)).toBeInTheDocument()
  })

  it('需求洞察页标注计算口径，并把检索落空列为知识库盲区', async () => {
    gotoAuthed('/admin/insight')
    expect(await screen.findByText('检索意图分布')).toBeInTheDocument()
    // 三处口径必须随数据展示（意图/热点/景区归属）
    expect(screen.getByText(/非前端猜测/)).toBeInTheDocument()
    expect(screen.getByText(/中文二元组词频（未引入分词器）/)).toBeInTheDocument()
    expect(screen.getByText(/非语义归属/)).toBeInTheDocument()
    // 盲区是可执行清单，必须渲染出来
    expect(screen.getByText('知识库盲区')).toBeInTheDocument()
    expect(screen.getByText('这个景区适合带孩子玩吗')).toBeInTheDocument()
    expect(screen.getByText(/1 条检索无命中/)).toBeInTheDocument()
  })

  it('数据查询页渲染表格与导出，并声明不解析自然语言', async () => {
    gotoAuthed('/admin/query')
    // 「数据查询」在侧栏与本页标题各出现一次
    expect((await screen.findAllByText('数据查询')).length).toBeGreaterThanOrEqual(2)
    // 这条声明是页面存在的理由：不假装支持 NL 问数。
    // 页头描述与说明块各写了一次（有意重复强调），故用 getAll
    expect(screen.getAllByText(/不解析自然语言/).length).toBeGreaterThanOrEqual(2)
    expect(await screen.findByText('拙政园')).toBeInTheDocument()
    expect(screen.getByText('灵隐飞来峰')).toBeInTheDocument()
    expect(screen.getByText(/导出 CSV（2 行）/)).toBeInTheDocument()
  })

  it('快捷指令工作台给出工单16 §2.2 的五项指令', async () => {
    gotoAuthed('/admin/commands')
    // 侧栏与本页标题各出现一次
    expect((await screen.findAllByText('快捷指令工作台')).length).toBeGreaterThanOrEqual(2)
    for (const label of ['资源挖掘', '场景创意', '文化创新', '数字营销', '效益提升']) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
    // 模板要可见可改，而不是藏起来的黑盒按钮
    expect(screen.getAllByText('先改再发').length).toBe(5)
    // 助理答的是知识库而非经营数据，这条边界必须说明
    expect(screen.getByText(/不产出结构化经营报表/)).toBeInTheDocument()
  })
})
