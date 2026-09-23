/**
 * 工单16-20 延伸 · 平台化双端重构（批次 0）
 * 路由注册表 —— 导航与路由的唯一事实源。
 *
 * 双端共 19 条路由。导航与路由表若各写一份必然漂移（改路由忘导航 → 死链），
 * 因此集中注册：导航由本表推导，「建设中」页面直接读取本表的工单依据。
 * 依据：docs/08-平台化双端前端重构执行方案.md §3.4
 */

export type AppSide = 'toc' | 'tob'

export type RouteEntry = {
  /** 路由路径，与 react-router 的 path 一致 */
  path: string
  side: AppSide
  /** ToB 侧栏分组名；ToC 不使用 */
  group?: string
  label: string
  /** 对应工单条目（用于说明该模块的来源，避免"凭空占位"） */
  ticket: string
  /** 对应工单16 的功能场景编号，如 S1 */
  scene?: string
  /** 是否出现在主导航；详情页与落地页这类只能从上下文进入的路由为 false */
  inNav?: boolean
  /** 导航精确匹配（首页用） */
  end?: boolean
  /** ToC 移动端底部 Tab 的字形 */
  glyph?: string
}

export const ROUTES: RouteEntry[] = [
  // ---------------- ToC 游客端 ----------------
  // 首页是"平台入口 + 建设进度"，不作为底部 Tab；"发现"指向真正的浏览页 /explore，
  // 首页本身仍可从左上角品牌标识进入。这样底部 Tab 的语义与页面职责一致。
  { path: '/', side: 'toc', label: '首页', ticket: '工单16 §2.2' },
  { path: '/explore', side: 'toc', label: '发现', ticket: '工单17 §2', scene: 'S1', inNav: true, end: true, glyph: '◎' },
  { path: '/park/:id', side: 'toc', label: '景区详情', ticket: '工单17 §2' },
  { path: '/guide', side: 'toc', label: '导览', ticket: '工单18 §1', scene: 'S2', inNav: true, glyph: '◈' },
  // 问答不再占用底部 Tab（docs/09 §4.3 定的是「发现/导览/行程/票务/我的」五格），
  // 改由导览页给出入口 —— 两者同属"与数字人对话"这一件事，放在一起语义也更顺。
  { path: '/ask', side: 'toc', label: '问答', ticket: '工单17 §1', scene: 'S1' },
  { path: '/plan', side: 'toc', label: '行程', ticket: '工单19 §1', scene: 'S4', inNav: true, glyph: '≡' },
  { path: '/create', side: 'toc', label: '创作', ticket: '工单19 §2', scene: 'S5' },
  { path: '/activity', side: 'toc', label: '活动', ticket: '工单19 §3', scene: 'S6' },
  { path: '/map', side: 'toc', label: '地图', ticket: '工单20 场景13' },
  // 票务大厅：列出各景区与起价，进入后选票种与时段（docs/09 G3）
  { path: '/tickets', side: 'toc', label: '票务', ticket: 'docs/09 G3', inNav: true, glyph: '✦' },
  { path: '/tickets/:parkId', side: 'toc', label: '门票预订', ticket: 'docs/09 G3' },
  // 下单深链：运营在推文/短信里发出去的链接只带一个时段 id，由此还原上下文
  { path: '/booking/:slotId', side: 'toc', label: '锁定场次', ticket: 'docs/09 G3' },
  { path: '/me', side: 'toc', label: '我的', ticket: '工单19 §4', scene: 'S7', inNav: true, glyph: '☺' },
  // 订单、电子票与评价合并在这一页：三者都围绕"我的一次游玩"，
  // 拆成 /me/orders、/me/tickets、/me/orders/:id/review 三个路由会让改评分要跳两级。
  { path: '/me/orders', side: 'toc', label: '我的订单', ticket: 'docs/09 G3' },
  { path: '/feedback', side: 'toc', label: '评价与反馈', ticket: 'docs/09 G4' },
  { path: '/s/:token', side: 'toc', label: '分享', ticket: '工单19 §4', scene: 'S7' },

  // ---------------- ToB 运营控制台 ----------------
  { path: '/admin', side: 'tob', group: '总览', label: '控制台总览', ticket: '工单16 §2.1', inNav: true, end: true },
  // 唯一免鉴权页面：必须挂在 TobShell 守卫之外（App.tsx 单独装配），
  // 故不设 group 也不进导航。
  { path: '/admin/login', side: 'tob', label: '运营端登录', ticket: '工单16 §5' },
  { path: '/admin/kb', side: 'tob', group: '内容', label: '知识库管理', ticket: '工单17 §2.2', scene: 'S8', inNav: true },
  { path: '/admin/content', side: 'tob', group: '内容', label: '内容生产与发布', ticket: '工单16 §2.2', scene: 'S8', inNav: true },
  { path: '/admin/parks', side: 'tob', group: '景区', label: '景区与景点管理', ticket: 'docs/09 G1/G2', inNav: true },
  // 分组必须在数组中**连续出现**：tobNavGroups 只与"最后一个分组"合并，
  // 把同组条目拆开插入会生成两个同名分组。
  { path: '/admin/tickets', side: 'tob', group: '票务', label: '票种与库存', ticket: 'docs/09 G3', inNav: true },
  { path: '/admin/orders', side: 'tob', group: '票务', label: '订单管理', ticket: 'docs/09 G3', inNav: true },
  { path: '/admin/checkin', side: 'tob', group: '票务', label: '核销台', ticket: 'docs/09 G3', inNav: true },
  { path: '/admin/service', side: 'tob', group: '服务', label: '游客服务工单', ticket: 'docs/09 G4', inNav: true },
  { path: '/admin/query', side: 'tob', group: '数据', label: '数据查询', ticket: '工单16 §2.2', scene: 'S8', inNav: true },
  { path: '/admin/insight', side: 'tob', group: '数据', label: '游客需求洞察', ticket: '工单16 §2.1 第4条', inNav: true },
  { path: '/admin/analytics', side: 'tob', group: '数据', label: '经营分析', ticket: 'docs/09 G5', inNav: true },
  { path: '/admin/review', side: 'tob', group: '治理', label: '审核与合规', ticket: '工单17 §5', inNav: true },
  { path: '/admin/users', side: 'tob', group: '治理', label: '用户与权限', ticket: '工单16 §5', inNav: true },
  { path: '/admin/commands', side: 'tob', group: '工具', label: '快捷指令工作台', ticket: '工单16 §2.2', scene: 'S9', inNav: true },
]

export type NavItem = { to: string; label: string; glyph: string; end?: boolean }

/** ToC 导航：由注册表推导，避免与路由表漂移 */
export const tocNav: NavItem[] = ROUTES.filter((route) => route.side === 'toc' && route.inNav).map(
  (route) => ({ to: route.path, label: route.label, glyph: route.glyph ?? '·', end: route.end }),
)

export type NavGroup = { title: string; items: { to: string; label: string; end?: boolean }[] }

/** ToB 侧栏：按 group 聚合，保持注册表中的出现顺序 */
export const tobNavGroups: NavGroup[] = ROUTES.filter((route) => route.side === 'tob' && route.inNav).reduce<
  NavGroup[]
>((groups, route) => {
  const title = route.group ?? '其他'
  const last = groups[groups.length - 1]
  const item = { to: route.path, label: route.label, end: route.end }
  if (last && last.title === title) last.items.push(item)
  else groups.push({ title, items: [item] })
  return groups
}, [])

/** 按路径取注册信息，「建设中」页面与路由装配共用 */
export const findRoute = (path: string): RouteEntry | undefined => ROUTES.find((route) => route.path === path)
