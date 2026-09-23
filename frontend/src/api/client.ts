/**
 * 工单18 · 后端接口客户端
 * 通过 Vite 代理访问阶段二/三后端（/api/v1）
 */
import { clearSession, getToken } from '../shared/utils/auth'

export interface ApiResponse<T> {
  code: number
  message: string
  data: T
  trace_id: string
}

export interface Viseme {
  t: number
  viseme: string
  char: string
}

export interface AvatarDrive {
  avatar_id: string
  emotion: string
  style: string
  motion: string
  /**
   * 语音数据。为 null 表示语音合成不可用（云端额度/网络异常）时的降级：
   * 数字人仍按 visemes + duration_ms 演示口型与动作，只是没有声音。
   */
  audio: { format: string; base64: string | null; size_bytes: number | null; provider: string } | null
  visemes: Viseme[]
  duration_ms: number
  lipsync: string
  /** 降级原因（空串表示正常），便于界面如实提示游客 */
  degraded?: string
}

export interface AvatarProfile {
  avatar_id: string
  name: string
  type: string
  engine: Record<string, string>
  voice: { provider: string }
  lipsync: { provider: string; viseme_set: string[] }
  emotions: string[]
  motions: string[]
  asset_note: string
}

export interface Citation {
  kb_id: string
  title: string
  source: string
  score: number
  rerank_score: number | null
}

export interface Detection {
  label: string
  score: number
  box: number[]
  track_id: number | null
}

export interface Gesture {
  name: string
  score: number
  handedness: string
  wave: boolean
}

export interface Expression {
  name: string
  score: number
  blendshapes: Record<string, number>
}

export interface PerceptionData {
  /** 图像分类：整图级标签，无位置框（与检测分开，避免零尺寸框污染画面） */
  classification?: { label: string; score: number }[]
  detections: Detection[]
  segments: { label: string; score: number; area_ratio: number }[]
  gestures: Gesture[]
  expression: Expression | null
}

export interface Suggestion {
  action: string
  motion: string
  text: string
  gesture: string
  confidence: number
}

export interface DialogResult {
  session_id: string
  intent: string
  question: string
  answer_text: string
  citations: Citation[]
  medias: { type: string; url: string }[]
  ocr_text: string | null
  asr_text: string | null
  perception: (PerceptionData & { suggestion?: Suggestion | null }) | null
  avatar: AvatarDrive | null
  session_turns: number
  lang: string
  workflow: string
}

const BASE = '/api/v1'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // 批次 4：控制台接口（/kb、/audit/*）要求运营及以上角色，统一在此注入令牌，
  // 避免每个调用点各写一遍 Authorization 而漏掉某处。
  // 用 Headers 合并而不是覆盖，保留调用方自带的 Content-Type。
  const headers = new Headers(init?.headers)
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(BASE + path, { ...init, headers })
  if (!response.ok) {
    // 令牌失效（过期/被拒）时立即清空登录态，让路由守卫把用户带回登录页，
    // 否则界面会停在"权限不足"的死状态上，用户无从恢复。
    if (response.status === 401) clearSession()
    let detail = `${response.status} ${response.statusText}`
    try {
      const body = await response.json()
      // 后端统一响应体用 message 承载可读信息，兼容 FastAPI 默认的 detail
      const readable = body?.message || body?.detail
      if (readable) detail = String(readable)
    } catch {
      /* 忽略非 JSON 响应 */
    }
    throw new Error(detail)
  }
  const payload = (await response.json()) as ApiResponse<T>
  if (payload.code !== 0) throw new Error(payload.message)
  return payload.data
}

export const api = {
  readyz: () => request<Record<string, unknown>>('/readyz'),
  stack: () => request<Record<string, unknown>>('/stack'),
  avatarProfile: () => request<AvatarProfile>('/avatar'),
  greet: (gesture: string) =>
    request<{ text: string; gesture: string; drive: AvatarDrive }>('/avatar/greet', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ gesture }),
    }),
  drive: (text: string, emotion?: string, motion?: string) =>
    request<AvatarDrive>('/avatar/drive', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, emotion, motion }),
    }),
  dialog: (body: { session_id?: string; text: string; with_avatar?: boolean; with_perception?: boolean }) =>
    request<DialogResult>('/dialog', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  dialogMultimodal: (form: FormData) =>
    request<DialogResult>('/dialog/multimodal', { method: 'POST', body: form }),
  session: (sessionId: string) => request<Record<string, unknown>>(`/session/${sessionId}`),

  // ---------------- 阶段四（工单19）· 创意策划与内容生成 ----------------
  planItinerary: (body: {
    interests: string[]
    theme?: string
    duration?: string
    companions?: string
    pace?: string
    start_point?: string
  }) =>
    request<ItineraryPlan>('/itinerary/plan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  recommendActivity: (body: {
    interests?: string[]
    keyword?: string
    latitude?: number | null
    longitude?: number | null
    radius_m?: number
    limit?: number
  }) =>
    request<ActivityRecommend>('/activity/recommend', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  createGuide: (body: { activity_id?: string; activity_name?: string; interests?: string[] }) =>
    request<GuideResult>('/create/guide', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  /** 纪念图片：默认异步，返回 CreationTask；background=false 时直接返回 CreationAsset */
  createImage: (form: FormData) => request<CreationAsset | CreationTask>('/create/image', { method: 'POST', body: form }),
  createVideo: (form: FormData) => request<CreationAsset | CreationTask>('/create/video', { method: 'POST', body: form }),
  createDiary: (body: { title?: string; tone?: string; place?: string; highlights?: string[] }) =>
    request<CreationAsset>('/create/diary', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  /** 导览地图（工单20 场景13）：坐标由后端按景点名查 PostGIS 补齐，前端只传站名与顺序 */
  createMap: (body: { title?: string; subtitle?: string; stops: { name: string; index?: number }[] }) =>
    request<CreationAsset>('/create/map', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  createAssets: (kind?: string) =>
    request<{ items: CreationAsset[]; total: number }>(`/create/assets${kind ? `?kind=${kind}` : ''}`),
  creationTask: (taskId: string) => request<CreationTask>(`/create/task/${taskId}`),
  share: (body: { asset_id?: string; plan_id?: string; channel?: string; title?: string; summary?: string; text?: string }) =>
    request<ShareResult>('/share', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  shareView: (token: string) => request<ShareView>(`/share/${token}`),

  // ---------------- docs/09 通用化（G1）· 目的地与景区 ----------------
  destinations: () => request<{ items: Destination[]; total: number }>('/destination'),
  parks: (params: ParkQuery = {}) => {
    const query = new URLSearchParams()
    if (params.destination_id) query.set('destination_id', params.destination_id)
    if (params.keyword) query.set('keyword', params.keyword)
    if (params.tag) query.set('tag', params.tag)
    if (params.limit) query.set('limit', String(params.limit))
    // 坐标用于"附近的景区"；不传则后端不做距离排序
    if (params.near_lat != null && params.near_lon != null) {
      query.set('near_lat', String(params.near_lat))
      query.set('near_lon', String(params.near_lon))
    }
    const suffix = query.toString()
    return request<{ items: ParkSummary[]; total: number; has_geo: boolean }>(`/park${suffix ? `?${suffix}` : ''}`)
  },
  park: (parkId: string) => request<ParkDetail>(`/park/${parkId}`),

  // ---------------- 工单16 §5 · 运营端身份与权限（批次 4） ----------------
  /** OAuth2 密码模式取令牌。后端用 OAuth2PasswordRequestForm，必须是表单编码而不是 JSON */
  login: (username: string, password: string) =>
    request<TokenResult>('/auth/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ username, password, grant_type: 'password' }),
    }),

  // ---------------- 工单17 §2.2 · 知识库管理（批次 4） ----------------
  kbList: (params: { limit?: number; offset?: number } = {}) => {
    const query = new URLSearchParams()
    if (params.limit != null) query.set('limit', String(params.limit))
    if (params.offset != null) query.set('offset', String(params.offset))
    const suffix = query.toString()
    return request<KbPage>(`/kb${suffix ? `?${suffix}` : ''}`)
  },
  kbGet: (chunkId: string) => request<KbChunk>(`/kb/${chunkId}`),
  kbUpdate: (chunkId: string, patch: Partial<Pick<KbChunk, 'title' | 'content' | 'modality' | 'media_uri' | 'source' | 'tags'>>) =>
    request<KbChunk>(`/kb/${chunkId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    }),
  kbDelete: (chunkId: string) => request<{ deleted: string }>(`/kb/${chunkId}`, { method: 'DELETE' }),
  kbIngest: (payload: {
    document_title?: string
    source?: string
    chunks: { id?: string; title: string; content: string; modality?: string; media_uri?: string; tags?: string[]; source?: string; authority?: string }[]
  }) =>
    request<{ ingested: number; text: number; clip_text: number; media: number }>('/kb/ingest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  /** 上传文档 → 后端存档 → Celery 解析分块入库（异步，返回 task_id） */
  kbIngestFile: (form: FormData) => request<KbIngestTask>('/kb/ingest/file', { method: 'POST', body: form }),

  // ---------------- 工单17 §5 / 工单20 · 审计与合规（批次 4） ----------------
  auditLogs: (params: { limit?: number; path?: string } = {}) => {
    const query = new URLSearchParams()
    if (params.limit != null) query.set('limit', String(params.limit))
    if (params.path) query.set('path', params.path)
    const suffix = query.toString()
    return request<{ items: AuditLogItem[]; total: number }>(`/audit/logs${suffix ? `?${suffix}` : ''}`)
  },
  compliance: () => request<{ checks: ComplianceCheck[]; pending: number }>('/audit/compliance'),

  // ---------------- 工单20 场景12 · 活动回顾 PPT（批次 4 内容生产） ----------------
  createPpt: (form: FormData) => request<CreationAsset>('/create/ppt', { method: 'POST', body: form }),
}

// ========================= 阶段四（工单19）类型 =========================
export interface ItineraryStop {
  index: number
  name: string
  start_time: string
  duration: string
  kind: string
  reason: string
  tips: string
  tags: string[]
}

export interface ItineraryPlan {
  plan_id: string | null
  title: string
  summary: string
  stops: ItineraryStop[]
  citations: Citation[]
  route_text: string
  workflow: string
}

export interface ActivityRecommendItem {
  id: string
  name: string
  schedule: string
  description: string
  how_to_join: string
  attraction: string
  distance_m: number | null
  match_score: number
  tags: string[]
}

export interface ActivityRecommend {
  items: ActivityRecommendItem[]
  advice: string
  has_geo: boolean
}

export interface GuideResult {
  title: string
  steps: string[]
  guide_text: string
  mermaid: string
  diagram_uri: string | null
  diagram_url: string | null
  asset_id?: string | null
  workflow?: string
}

export interface CreationAsset {
  id: string
  kind: string
  title: string
  status: string
  result_uri: string | null
  url: string | null
  text_content: string
  mime: string
  size_bytes: number
  prompt: string
  model: string
  extra: Record<string, unknown>
}

export interface CreationTask {
  task_id: string
  kind: string
  status: string
  progress: number
  message: string
  error?: string
  asset: CreationAsset | null
}

export interface ShareResult {
  token: string
  url: string
  title: string
  summary: string
  poster_uri: string | null
  poster_url: string | null
  expires_in: number
}

export interface ShareView {
  token: string
  title: string
  summary: string
  channel: string
  visits: number
  poster_url: string | null
  asset: {
    id: string
    kind: string
    title: string
    url: string | null
    mime: string
    text_content: string
  } | null
}

// ================= docs/09 通用化（G1）：目的地 / 景区 =================
export interface Destination {
  id: string
  name: string
  region: string
  summary: string
  description: string
  tags: string[]
  park_count: number
}

export interface ParkSummary {
  id: string
  name: string
  destination_id: string | null
  destination_name: string | null
  summary: string
  description: string
  open_hours: string
  /** open 营业 / closed 闭园 / maintenance 维护（本项目补充定义） */
  status: string
  daily_capacity: number
  level: string
  ticket_notice: string
  cover_uri: string | null
  tags: string[]
  attraction_count: number
  /** 传了坐标才有值，单位米 */
  distance_m: number | null
}

export interface ParkAttraction {
  id: string
  name: string
  summary: string
  description: string
  open_hours: string
  tags: string[]
  park_id: string | null
}

export interface ParkActivityItem {
  id: string
  name: string
  schedule: string
  description: string
  how_to_join: string
  attraction_id: string | null
}

export interface ParkDetail extends ParkSummary {
  destination: { id: string; name: string; region: string } | null
  attractions: ParkAttraction[]
  activities: ParkActivityItem[]
}

export interface ParkQuery {
  destination_id?: string
  keyword?: string
  tag?: string
  limit?: number
  near_lat?: number
  near_lon?: number
}

// ============ 批次 4 · 运营控制台（工单16 §5 / 工单17 §2.2 / §5） ============

/** /auth/token 的返回体（对应后端 schemas.TokenOut） */
export interface TokenResult {
  access_token: string
  token_type?: string
  expires_in: number
  role: string
}

/** 知识条目（对应后端 services/kb.py 的 _to_dict） */
export interface KbChunk {
  id: string
  title: string
  content: string
  /** text 文本 / image 图像 / video 视频 / audio 音频 */
  modality: string
  media_uri: string
  tags: string[]
  source: string
}

export interface KbPage {
  items: KbChunk[]
  total: number
  limit: number
  offset: number
}

/** 文档入库为异步任务，返回 Celery task_id */
export interface KbIngestTask {
  task_id: string
  uri: string
  filename: string | null
}

/** 审计日志条目（对应 /audit/logs 的 items） */
export interface AuditLogItem {
  id: string
  method: string
  /** 已脱敏的请求路径 */
  path: string
  status: number | null
  client_ip: string | null
  role: string | null
  trace_id: string | null
  created_at: string | null
}

/** 合规自查项。后端刻意不粉饰：未配置项为 pending */
export interface ComplianceCheck {
  item: string
  status: 'ok' | 'pending' | string
  detail: string
}

/** 知识模态 → 中文标签与语义色（列表与筛选共用一套口径） */
export const KB_MODALITY: Record<string, { label: string; tone: 'ok' | 'warn' | 'down' | 'idle' }> = {
  text: { label: '文本', tone: 'ok' },
  image: { label: '图像', tone: 'warn' },
  video: { label: '视频', tone: 'down' },
  audio: { label: '音频', tone: 'idle' },
}

/** HTTP 状态码 → 语义色（审计日志用） */
export const httpTone = (status: number | null): 'ok' | 'warn' | 'down' | 'idle' => {
  if (status == null) return 'idle'
  if (status < 300) return 'ok'
  if (status < 400) return 'warn'
  return 'down'
}


/** 营业状态 → 中文与语义色（管理端与游客端共用一套口径） */
export const PARK_STATUS: Record<string, { label: string; tone: 'ok' | 'warn' | 'down' }> = {
  open: { label: '营业中', tone: 'ok' },
  closed: { label: '已闭园', tone: 'down' },
  maintenance: { label: '维护中', tone: 'warn' },
}

/** 距离展示：米 → 千米，保留一位小数 */
export const formatDistance = (meters: number | null): string =>
  meters == null ? '' : meters < 1000 ? `${Math.round(meters)} m` : `${(meters / 1000).toFixed(1)} km`

/**
 * 轮询异步生成任务直到结束。
 * AIGC 图像生成实测 30~40s、视频合成 5~15s，因此采用轮询而不是长连接：
 * 实现简单、断线可恢复，也避免在浏览器侧占用一条长连接。
 */
export async function pollCreationTask(
  taskId: string,
  onTick?: (task: CreationTask) => void,
  intervalMs = 2500,
  timeoutMs = 300000,
): Promise<CreationTask> {
  const deadline = Date.now() + timeoutMs
  for (;;) {
    const task = await api.creationTask(taskId)
    onTick?.(task)
    if (task.status === 'success' || task.status === 'failed') return task
    if (Date.now() > deadline) throw new Error('生成超时，请稍后在「我的创作」中查看结果')
    await new Promise((resolve) => window.setTimeout(resolve, intervalMs))
  }
}

/** 后端返回的产物访问地址（相对 /api/v1），前端页面同源，直接可用 */
export const assetUrl = (path: string | null | undefined) => (path ? path : '')

/**
 * 唇形视位对应的张口度（与后端 VISEMES 一致）。
 *
 * 取值范围刻意收窄（0.05~0.72）：真人说话时下颌并不会在音节之间完全闭合，
 * 只有双唇音（b/p/m）才真正闭口；通用辅音 C 保留约 1/4 开口，
 * 否则每 190ms 就会在 0.05↔0.85 之间大幅摆动，看起来像在喘气。
 */
export const VISEME_OPEN: Record<string, number> = {
  sil: 0.06,
  M: 0.05,
  F: 0.26,
  C: 0.34,
  I: 0.4,
  U: 0.48,
  E: 0.58,
  O: 0.7,
  A: 0.8,
}

/**
 * 视位时长权重：元音开口时间长、辅音与静音短。
 * 后端视位是按「每字符等长」盲生成的，直接播放会得到机械的匀速口型；
 * 这里按类型加权后再整体拟合到音频真实时长，口型节奏才自然。
 */
const VISEME_WEIGHT: Record<string, number> = {
  sil: 0.55,
  M: 0.7,
  F: 0.75,
  C: 0.75,
  A: 1.3,
  O: 1.25,
  E: 1.12,
  I: 1.0,
  U: 1.08,
}

const clamp01 = (value: number) => Math.min(1, Math.max(0, value))
const smooth = (p: number) => p * p * (3 - 2 * p)

/**
 * 播放数字人语音并按时间轴驱动唇形。
 *
 * 关键点：口型以**音频真实播放位置**（currentTime）为时钟逐帧采样，
 * 而不是按预排的 setTimeout 走表——后者一旦音频起播延迟或缓冲就会整体错位。
 * 时间轴同时按音频真实时长重定向，因此唇形与声音始终同源同步。
 *
 * 返回停止函数；音频缺失时退化为用 performance.now() 计时（不影响动画演示）。
 */
export function playDrive(
  drive: AvatarDrive,
  onViseme: (viseme: string | null, open: number) => void,
): () => void {
  const visemes = drive.visemes ?? []
  if (!visemes.length) return () => undefined

  // 1) 按视位类型加权并累计，得到归一化边界
  const cumulative: number[] = []
  let totalWeight = 0
  for (const item of visemes) {
    totalWeight += VISEME_WEIGHT[item.viseme] ?? 1
    cumulative.push(totalWeight)
  }
  if (totalWeight <= 0) totalWeight = 1

  // 2) 拟合到音频真实时长（取 94%，留出收尾）
  let spanMs = Math.max(400, (drive.duration_ms || 1200) * 0.94)
  const base64 = drive.audio?.base64
  const audio = base64 ? new Audio(`data:audio/${drive.audio?.format || 'mp3'};base64,${base64}`) : null
  const retime = () => {
    if (audio && Number.isFinite(audio.duration) && audio.duration > 0.35) spanMs = audio.duration * 1000 * 0.94
  }
  if (audio) {
    audio.addEventListener('loadedmetadata', retime)
    audio.addEventListener('durationchange', retime)
    void audio.play().catch(() => undefined)
    retime()
  }

  let stopped = false
  let raf = 0
  const fallbackStart = performance.now()
  const deadline = () => spanMs / 0.94 + 300

  /** 采样某一时刻的口型开合度（含协同发音过渡，避免视位硬切） */
  const sample = (ms: number) => {
    let cursor = 0
    let index = visemes.length - 1
    for (let i = 0; i < visemes.length; i += 1) {
      const boundary = (cumulative[i] / totalWeight) * spanMs
      if (ms < boundary) {
        index = i
        break
      }
      cursor = boundary
    }
    const end = (cumulative[index] / totalWeight) * spanMs
    const progress = clamp01((ms - cursor) / Math.max(1, end - cursor))
    const current = VISEME_OPEN[visemes[index].viseme] ?? 0.1
    const upcoming = VISEME_OPEN[visemes[index + 1]?.viseme ?? 'sil'] ?? 0.08
    // 后 40% 提前向下一个视位过渡，形成连续的口型变化
    const blend = progress < 0.6 ? 0 : smooth((progress - 0.6) / 0.4)
    return { viseme: visemes[index].viseme as string | null, open: current + (upcoming - current) * blend }
  }

  const loop = () => {
    if (stopped) return
    const ms = audio ? audio.currentTime * 1000 : performance.now() - fallbackStart
    if ((audio && audio.ended) || ms > deadline()) {
      onViseme(null, 0)
      return
    }
    const { viseme, open } = sample(ms)
    onViseme(viseme, open)
    raf = requestAnimationFrame(loop)
  }
  raf = requestAnimationFrame(loop)

  return () => {
    stopped = true
    cancelAnimationFrame(raf)
    if (audio) {
      audio.removeEventListener('loadedmetadata', retime)
      audio.removeEventListener('durationchange', retime)
      audio.pause()
      audio.src = ''
    }
    onViseme(null, 0)
  }
}
