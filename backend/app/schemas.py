"""工单17 · 接口契约（对应 docs/03 第六章接口设计）

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class ApiResponse(BaseModel):
    code: int = 0
    message: str = "ok"
    data: Any = None
    trace_id: str = ""

    @model_validator(mode="after")
    def _bind_request_trace(self) -> "ApiResponse":
        """把响应体的 trace_id 收敛为**请求级** trace_id（工单20 · 全链路贯穿）。

        各路由历史上写作 `trace_id=uuid.uuid4().hex`，每次调用都会新生成一个 id，
        无法与访问日志、审计记录、上游调用串起来。这里统一改由请求上下文（中间件注入）
        决定，路由侧无需改动，也不影响中间件缺位时的独立使用（此时保留原值）。
        """
        from .core.observability import get_trace_id

        current = get_trace_id()
        if current:
            self.trace_id = current
        return self


# ---------------- 授权 ----------------
class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str


# ---------------- 知识库 ----------------
class ChunkIn(BaseModel):
    id: str | None = None
    title: str
    content: str
    modality: str = "text"
    media_uri: str | None = None
    tags: list[str] = Field(default_factory=list)
    source: str = ""
    authority: str = ""


class IngestRequest(BaseModel):
    document_title: str = ""
    source: str = ""
    chunks: list[ChunkIn]


class ChunkOut(BaseModel):
    id: str
    title: str
    content: str
    modality: str
    media_uri: str | None = None
    tags: list[str] = Field(default_factory=list)
    source: str = ""


# ---------------- 检索 ----------------
class TextSearchRequest(BaseModel):
    query: str
    top_k: int | None = None
    tags: list[str] | None = None


class HitOut(BaseModel):
    kb_id: str
    title: str
    content: str
    modality: str
    media_uri: str | None = None
    tags: list[str] = Field(default_factory=list)
    source: str = ""
    score: float
    rerank_score: float | None = None


class SearchData(BaseModel):
    mode: str
    hits: list[HitOut]
    ocr_text: str | None = None
    ocr_blocks: list[dict] | None = None


# ---------------- 问答 ----------------
class QueryRequest(BaseModel):
    query: str
    top_k: int | None = None
    rerank_top_n: int | None = None
    tags: list[str] | None = None
    lang: str = "zh"


class Citation(BaseModel):
    kb_id: str
    title: str
    source: str = ""
    score: float = 0.0
    rerank_score: float | None = None


class QueryData(BaseModel):
    answer_text: str
    citations: list[Citation] = Field(default_factory=list)
    medias: list[dict] = Field(default_factory=list)
    ocr_text: str | None = None
    lang: str = "zh"
    workflow: str = "langgraph:retrieve→rerank→generate"


# ---------------- 媒体 ----------------
class TTSRequest(BaseModel):
    text: str
    lang: str = "zh"
    voice: str = "default"


class SubtitleRequest(BaseModel):
    text: str
    lang: str = "zh"
    target_langs: list[str] = Field(default_factory=lambda: ["zh", "en"])


class UploadOut(BaseModel):
    uri: str
    key: str
    media_type: str
    size_bytes: int


# ========================= 阶段三（工单18）新增 =========================
class SessionCreateRequest(BaseModel):
    lang: str = "zh"


class DialogRequest(BaseModel):
    session_id: str | None = None
    text: str
    lang: str = "zh"
    with_avatar: bool = True
    with_perception: bool = True


class AvatarDriveRequest(BaseModel):
    text: str
    lang: str = "zh"
    emotion: str | None = None
    motion: str | None = None


class AvatarGreetRequest(BaseModel):
    gesture: str | None = "挥手"
    lang: str = "zh"


# ========================= 阶段四（工单19）新增 =========================
# ---------------- 个性化线路与活动生成 ----------------
class ItineraryPlanRequest(BaseModel):
    """游客画像输入：兴趣偏好、旅行主题、时间安排（工单19 §3.1）。"""

    interests: list[str] = Field(default_factory=lambda: ["历史", "美食"])
    theme: str = "文化深度游"
    duration: str = "半日"          # 半日 | 一日 | 两日
    companions: str = "独自"        # 独自 | 亲子 | 情侣 | 长辈 | 朋友
    pace: str = "适中"              # 紧凑 | 适中 | 舒缓
    start_point: str = "景区主入口"
    session_id: str | None = None
    lang: str = "zh"


class ItineraryStop(BaseModel):
    index: int
    name: str
    start_time: str = ""
    duration: str = ""
    kind: str = "sight"             # sight | food | activity | rest | photo
    reason: str = ""
    tips: str = ""
    tags: list[str] = Field(default_factory=list)


class ItineraryData(BaseModel):
    plan_id: str | None = None
    title: str
    summary: str = ""
    stops: list[ItineraryStop] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    route_text: str = ""            # 行程单（纯文本，可下载分享）
    workflow: str = "langgraph:profile→retrieve→plan→format"


# ---------------- 活动与体验推荐 ----------------
class ActivityRecommendRequest(BaseModel):
    session_id: str | None = None
    interests: list[str] = Field(default_factory=list)
    keyword: str = ""
    latitude: float | None = None
    longitude: float | None = None
    radius_m: int = 1500
    limit: int = 5


class ActivityItem(BaseModel):
    id: str
    name: str
    schedule: str = ""
    description: str = ""
    how_to_join: str = ""
    attraction: str = ""
    distance_m: float | None = None
    match_score: float = 0.0
    tags: list[str] = Field(default_factory=list)


class ActivityData(BaseModel):
    items: list[ActivityItem] = Field(default_factory=list)
    advice: str = ""
    has_geo: bool = False


class GuideRequest(BaseModel):
    """活动参与攻略 + 体验流程图（工单19 §3.3）。"""

    activity_id: str | None = None
    activity_name: str = ""
    interests: list[str] = Field(default_factory=list)
    session_id: str | None = None


class GuideData(BaseModel):
    title: str
    steps: list[str] = Field(default_factory=list)
    guide_text: str = ""
    mermaid: str = ""
    diagram_uri: str | None = None
    diagram_url: str | None = None
    citations: list[Citation] = Field(default_factory=list)


# ---------------- 纪念内容生成 ----------------
class CreationAssetOut(BaseModel):
    id: str
    kind: str
    title: str = ""
    status: str = "success"
    result_uri: str | None = None
    url: str | None = None
    text_content: str = ""
    mime: str = ""
    size_bytes: int = 0
    prompt: str = ""
    model: str = ""
    extra: dict = Field(default_factory=dict)


class CreationTaskOut(BaseModel):
    task_id: str
    kind: str
    status: str = "pending"
    progress: int = 0
    message: str = ""
    asset: CreationAssetOut | None = None


class CreationVideoRequest(BaseModel):
    """短视频/电子相册的编排参数（照片以 multipart 上传）。"""

    title: str = "我的旅行回忆"
    captions: list[str] = Field(default_factory=list)
    seconds_per_image: float | None = None
    watermark: str = "文旅创新智脑"
    with_narration: bool = False   # 是否用 CosyVoice 生成解说音轨并混入


class DiaryRequest(BaseModel):
    title: str = "我的旅行日记"
    tone: str = "温暖记录"          # 温暖记录 | 文艺随笔 | 轻松活泼
    place: str = ""
    highlights: list[str] = Field(default_factory=list)


# ---------------- 导览地图（工单20 场景13）----------------
class MapStop(BaseModel):
    """地图分站：名称需与景点/活动数据一致，坐标由后端查 PostGIS 补齐。"""

    name: str
    index: int | None = None


class MapRequest(BaseModel):
    title: str = "个性化导览地图"
    subtitle: str = ""
    stops: list[MapStop] = Field(default_factory=list)


# ---------------- 分享 ----------------
class ShareRequest(BaseModel):
    asset_id: str | None = None
    plan_id: str | None = None
    channel: str = "link"           # link | poster | wechat | weibo
    title: str = ""
    summary: str = ""
    text: str = ""


class ShareData(BaseModel):
    token: str
    url: str
    title: str = ""
    summary: str = ""
    poster_uri: str | None = None
    poster_url: str | None = None
    expires_in: int = 0


class CreationListData(BaseModel):
    items: list[CreationAssetOut] = Field(default_factory=list)
    total: int = 0
