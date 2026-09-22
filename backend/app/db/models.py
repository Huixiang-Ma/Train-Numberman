"""工单17 · 业务数据模型（PostgreSQL 16 + PostGIS）

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成
对应 docs/03 第 4.1 节知识库数据模型：景点 / 文物建筑 / 人物 / 活动 / 故事 / 多模态素材 / 知识分块。
"""
from __future__ import annotations

import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Table, Text, Column, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


def _uuid() -> str:
    return uuid.uuid4().hex


# 多对多关联表
attraction_relic = Table(
    "attraction_relic",
    Base.metadata,
    Column("attraction_id", String(32), ForeignKey("attraction.id", ondelete="CASCADE"), primary_key=True),
    Column("relic_id", String(32), ForeignKey("relic.id", ondelete="CASCADE"), primary_key=True),
)

attraction_person = Table(
    "attraction_person",
    Base.metadata,
    Column("attraction_id", String(32), ForeignKey("attraction.id", ondelete="CASCADE"), primary_key=True),
    Column("person_id", String(32), ForeignKey("person.id", ondelete="CASCADE"), primary_key=True),
)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Destination(TimestampMixin, Base):
    """目的地（城市 / 区域）：通用化的最上层归属。

    工单17 §2.5 要求「支持本地化内容扩展，便于不同景区、城市的知识库定制」。
    原先只有扁平的 Attraction，装不下「多目的地、多景区」，因此引入
    目的地 → 景区 → 景点 三层；数字人能力不变，只是适用范围变宽。
    """

    __tablename__ = "destination"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(128), index=True)
    region: Mapped[str] = mapped_column(String(64), default="")  # 省 / 市
    summary: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    geom: Mapped[object | None] = mapped_column(Geometry(geometry_type="POINT", srid=4326), nullable=True)

    parks = relationship("Park", back_populates="destination")


class Park(TimestampMixin, Base):
    """景区：通用化的中间层。景点归属它，后续的票种 / 活动 / 服务工单也挂在它上面。"""

    __tablename__ = "park"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    destination_id: Mapped[str | None] = mapped_column(ForeignKey("destination.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    open_hours: Mapped[str] = mapped_column(String(128), default="")
    # 营业状态：open 营业 / closed 闭园 / maintenance 维护。工单未定义，本项目补充。
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    # 日承载量（人次）。工单16 §2.1「游客洞察」与承载预警需要。
    daily_capacity: Mapped[int] = mapped_column(Integer, default=0)
    level: Mapped[str] = mapped_column(String(32), default="")  # 5A / 4A / 省级 等
    ticket_notice: Mapped[str] = mapped_column(Text, default="")  # 票务须知
    cover_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    geom: Mapped[object | None] = mapped_column(Geometry(geometry_type="POINT", srid=4326), nullable=True)

    destination = relationship("Destination", back_populates="parks")
    attractions = relationship("Attraction", back_populates="park")


class Attraction(TimestampMixin, Base):
    """景点：含 PostGIS 地理坐标。"""

    __tablename__ = "attraction"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(128), index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    open_hours: Mapped[str] = mapped_column(String(128), default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    geom: Mapped[object | None] = mapped_column(Geometry(geometry_type="POINT", srid=4326), nullable=True)
    # 所属景区。可空：历史数据先落地，再由种子脚本回填归属（列级变更见 scripts/sync_schema.py）。
    park_id: Mapped[str | None] = mapped_column(ForeignKey("park.id"), nullable=True, index=True)

    park = relationship("Park", back_populates="attractions")
    relics = relationship("Relic", secondary=attraction_relic, back_populates="attractions")
    persons = relationship("Person", secondary=attraction_person, back_populates="attractions")
    activities = relationship("Activity", back_populates="attraction")


class Relic(TimestampMixin, Base):
    """文物 / 建筑。"""

    __tablename__ = "relic"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(128), index=True)
    category: Mapped[str] = mapped_column(String(64), default="")
    era: Mapped[str] = mapped_column(String(64), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    image_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)

    attractions = relationship("Attraction", secondary=attraction_relic, back_populates="relics")


class Person(TimestampMixin, Base):
    """人物。"""

    __tablename__ = "person"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(64), index=True)
    lifespan: Mapped[str] = mapped_column(String(64), default="")
    bio: Mapped[str] = mapped_column(Text, default="")

    attractions = relationship("Attraction", secondary=attraction_person, back_populates="persons")


class Activity(TimestampMixin, Base):
    """活动：含举办地点坐标。"""

    __tablename__ = "activity"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(128), index=True)
    schedule: Mapped[str] = mapped_column(String(256), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    how_to_join: Mapped[str] = mapped_column(Text, default="")
    attraction_id: Mapped[str | None] = mapped_column(ForeignKey("attraction.id"), nullable=True)
    geom: Mapped[object | None] = mapped_column(Geometry(geometry_type="POINT", srid=4326), nullable=True)

    attraction = relationship("Attraction", back_populates="activities")


class Story(TimestampMixin, Base):
    """故事 / 讲解素材。"""

    __tablename__ = "story"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(200), index=True)
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(200), default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    subject_type: Mapped[str] = mapped_column(String(32), default="")  # attraction | relic | person
    subject_id: Mapped[str | None] = mapped_column(String(32), nullable=True)


class MediaAsset(TimestampMixin, Base):
    """多模态素材（图片 / 视频 / 音频），文件存 MinIO。"""

    __tablename__ = "media_asset"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    modality: Mapped[str] = mapped_column(String(16), index=True)  # image | video | audio
    uri: Mapped[str] = mapped_column(String(512))
    mime: Mapped[str] = mapped_column(String(128), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    caption: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    subject_type: Mapped[str] = mapped_column(String(32), default="")
    subject_id: Mapped[str | None] = mapped_column(String(32), nullable=True)


class KbDocument(TimestampMixin, Base):
    """知识原始文档（采集入库的最小单元）。"""

    __tablename__ = "kb_document"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(200), index=True)
    source: Mapped[str] = mapped_column(String(200), default="")
    authority: Mapped[str] = mapped_column(String(64), default="")  # official | expert | publication
    lang: Mapped[str] = mapped_column(String(8), default="zh")
    tags: Mapped[list] = mapped_column(JSON, default=list)

    chunks = relationship("KbChunk", back_populates="document", cascade="all, delete-orphan")


class KbChunk(TimestampMixin, Base):
    """知识分块：embedding 存 Milvus，本表保存文本与引用关系。"""

    __tablename__ = "kb_chunk"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("kb_document.id", ondelete="CASCADE"), nullable=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    content: Mapped[str] = mapped_column(Text)
    modality: Mapped[str] = mapped_column(String(16), default="text", index=True)
    media_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(200), default="")
    score_hint: Mapped[float] = mapped_column(Float, default=0.0)
    vector_id: Mapped[str] = mapped_column(String(64), index=True)  # Milvus 主键

    document = relationship("KbDocument", back_populates="chunks")


# ==========================================================================
# 阶段四（工单19）· 创意策划与内容生成
# 对应 docs/05 第五章：行程策划 / 生成产物 / 异步任务 / 分享链接
# ==========================================================================
class ItineraryPlan(TimestampMixin, Base):
    """个性化线路与活动策划结果（工单19 §3.1）。

    保留输入画像与 LLM 原始输出，便于复现、二次编辑（§4.4）与效果回溯。
    """

    __tablename__ = "itinerary_plan"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    session_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    # 输入画像：兴趣 / 主题 / 时长 / 同行 / 节奏 / 起点
    interests: Mapped[list] = mapped_column(JSON, default=list)
    theme: Mapped[str] = mapped_column(String(128), default="")
    duration: Mapped[str] = mapped_column(String(64), default="")
    companions: Mapped[str] = mapped_column(String(64), default="")
    start_point: Mapped[str] = mapped_column(String(128), default="")
    # 输出：分站行程与引用来源
    stops: Mapped[list] = mapped_column(JSON, default=list)
    citations: Mapped[list] = mapped_column(JSON, default=list)
    model: Mapped[str] = mapped_column(String(64), default="")
    raw: Mapped[str] = mapped_column(Text, default="")


class CreationAsset(TimestampMixin, Base):
    """AIGC 生成产物：图片 / 视频 / 文本（工单19 §3.2）。

    记录生成所用的提示词与模型，满足「AIGC 内容合规」的溯源要求（docs/05 §九）。
    """

    __tablename__ = "creation_asset"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(String(32), index=True)  # artistic | postcard | group_photo | video | diary | poster | guide
    title: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(16), default="success", index=True)  # running | success | failed
    # 产物：图片/视频存 uri；文本类（日记/攻略）存 text_content
    result_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # 128 而非 64：OOXML 的 MIME 长达 73 字符
    # （application/vnd.openxmlformats-officedocument.presentationml.presentation），
    # 64 会在生成回顾 PPT 时触发 StringDataRightTruncation，产物落库失败。
    result_mime: Mapped[str] = mapped_column(String(128), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    text_content: Mapped[str] = mapped_column(Text, default="")
    # 输入与生成参数
    source_uris: Mapped[list] = mapped_column(JSON, default=list)
    prompt: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str] = mapped_column(String(64), default="")
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    session_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)


class CreationTask(TimestampMixin, Base):
    """异步生成任务（工单19 §五：AIGC 耗时长，统一走 Celery + Redis）。

    Celery 的结果后端只解决"结果可取"，无法支撑「我的创作」列表、配额统计与
    失败原因回看，因此用本表落一份任务状态；两者以 celery_task_id 关联。
    """

    __tablename__ = "creation_task"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    celery_task_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    kind: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(String(256), default="")
    asset_id: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    owner: Mapped[str] = mapped_column(String(64), default="guest", index=True)


class ShareLink(TimestampMixin, Base):
    """内容分享链接（工单19 §3.4）。"""

    __tablename__ = "share_link"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    token: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    asset_id: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    channel: Mapped[str] = mapped_column(String(32), default="link")  # link | poster | wechat | weibo
    title: Mapped[str] = mapped_column(String(200), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(String(512), default="")
    poster_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)
    visits: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ==========================================================================
# 阶段五（工单20）· 可观测与合规
# ==========================================================================
class AuditLog(TimestampMixin, Base):
    """操作审计日志（工单20 · docs/01 §七「操作日志 + 访问日志」）。

    只记录状态变更类请求（POST/PUT/PATCH/DELETE）。**不落请求体**：
    游客上传的照片与文本属个人信息，审计保留"谁在何时对哪个资源做了什么、结果如何"
    即可满足追溯要求，记录内容本身反而扩大泄露面。
    """

    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    method: Mapped[str] = mapped_column(String(8), index=True)
    path: Mapped[str] = mapped_column(String(256), index=True)
    status: Mapped[int] = mapped_column(Integer, default=0)
    client_ip: Mapped[str] = mapped_column(String(64), default="")  # 已脱敏
    role: Mapped[str] = mapped_column(String(32), default="guest")
    trace_id: Mapped[str] = mapped_column(String(32), index=True, default="")
