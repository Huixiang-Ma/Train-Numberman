"""docs/09 G4 · 游客服务与评价（批次 5）

工单编号：人工智能CV-AIGC-19-文旅Agent任务工单-创意策划与内容生成
对应 docs/09 §3.2「G4 游客服务：在线咨询、投诉建议、失物招领、紧急求助、满意度回访」
与 §4.1 的评价反馈。

两件事放在同一个服务里是有意的：**评价与工单是同一根链条的两端**。
投诉建议处理完会沉淀成评价的上下文，客服在同一页看到"这位游客投诉过什么、
给过几分"才能给出合适的答复。拆成两个服务会让这个关联在多处重复查询。
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select

from ..db.base import SessionLocal
from ..db.models import Review, ServiceRequest

logger = logging.getLogger(__name__)

CATEGORY_LABEL = {
    "consult": "咨询",
    "complaint": "投诉建议",
    "lost": "失物招领",
    "help": "紧急求助",
}

STATUS_LABEL = {
    "open": "待受理",
    "processing": "处理中",
    "resolved": "已回复",
    "closed": "已关闭",
}

# 处理优先级：紧急求助永远排在咨询前面，与提交时间无关。
# 现场安全事件晚处理一分钟与咨询晚处理一分钟，代价完全不对等。
PRIORITY = {"help": 0, "complaint": 1, "lost": 2, "consult": 3}


class ServiceRequestService:
    """游客服务工单的读写。"""

    def create(
        self,
        *,
        park_id: str | None,
        visitor_ref: str,
        category: str,
        content: str,
        contact: str = "",
        urgent: bool = False,
    ) -> tuple[dict | None, str | None]:
        if category not in CATEGORY_LABEL:
            return None, f"服务类型需为 {'/'.join(CATEGORY_LABEL)} 之一"
        if not content.strip():
            return None, "请填写具体内容"
        if len(content) > 2000:
            return None, "内容过长（上限 2000 字）"

        with SessionLocal() as db:
            row = ServiceRequest(
                id=uuid.uuid4().hex,
                park_id=park_id or None,
                visitor_ref=visitor_ref or "",
                category=category,
                content=content.strip(),
                contact=contact.strip(),
                # 紧急求助一律置 urgent：游客点进来时常来不及再勾一个"加急"复选框
                urgent=urgent or category == "help",
                status="open",
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return self._dict(row), None

    def list(
        self,
        *,
        park_id: str | None = None,
        status: str | None = None,
        category: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        with SessionLocal() as db:
            stmt = select(ServiceRequest)
            if park_id:
                stmt = stmt.where(ServiceRequest.park_id == park_id)
            if status:
                stmt = stmt.where(ServiceRequest.status == status)
            if category:
                stmt = stmt.where(ServiceRequest.category == category)
            rows = db.scalars(stmt.order_by(ServiceRequest.created_at.desc()).limit(limit)).all()

            items = [self._dict(row) for row in rows]
            # 排序在 Python 侧做：待受理优先、紧急优先、同类按时间倒序。
            # 这三条用一条 SQL 表达要引入 CASE 表达式，而量级（百位）不值得。
            #
            # 时间那一维不写进 key：上面的 SQL 查询已按 created_at 倒序取出，
            # 而 Python 的 sort 是**稳定**的，因此同键元素自然保持原有时间次序。
            status_rank = {"open": 0, "processing": 1, "resolved": 2, "closed": 3}
            items.sort(
                key=lambda item: (
                    status_rank.get(item["status"], 9),
                    0 if item["urgent"] else 1,
                    PRIORITY.get(item["category"], 9),
                )
            )
            return items

    def reply(self, request_id: str, reply: str, handled_by: str = "") -> dict | None:
        with SessionLocal() as db:
            row = db.get(ServiceRequest, request_id)
            if row is None:
                return None
            row.reply = reply.strip()
            row.handled_by = handled_by
            row.replied_at = datetime.now(timezone.utc)
            # 有回复即视为已回复；运营仍可再改为处理中或关闭
            row.status = "resolved" if reply.strip() else row.status
            db.commit()
            db.refresh(row)
            return self._dict(row)

    def set_status(self, request_id: str, status: str) -> tuple[dict | None, str | None]:
        if status not in STATUS_LABEL:
            return None, f"状态需为 {'/'.join(STATUS_LABEL)} 之一"
        with SessionLocal() as db:
            row = db.get(ServiceRequest, request_id)
            if row is None:
                return None, "工单不存在"
            row.status = status
            db.commit()
            db.refresh(row)
            return self._dict(row), None

    def stats(self, park_id: str | None = None) -> dict:
        with SessionLocal() as db:
            base = select(func.count()).select_from(ServiceRequest)
            if park_id:
                base = base.where(ServiceRequest.park_id == park_id)

            total = int(db.scalar(base) or 0)
            open_count = int(db.scalar(base.where(ServiceRequest.status == "open")) or 0)
            urgent_count = int(db.scalar(base.where(ServiceRequest.urgent.is_(True), ServiceRequest.status == "open")) or 0)
            resolved = int(db.scalar(base.where(ServiceRequest.status.in_(("resolved", "closed")))) or 0)

            by_category: dict[str, int] = {}
            for key in CATEGORY_LABEL:
                by_category[key] = int(db.scalar(base.where(ServiceRequest.category == key)) or 0)

            # 平均响应时长：只算已回复的，未回复的没有响应时长可言
            avg_seconds = db.scalar(
                select(func.avg(func.extract("epoch", ServiceRequest.replied_at - ServiceRequest.created_at))).where(
                    ServiceRequest.replied_at.isnot(None)
                )
            )

            return {
                "total": total,
                "open": open_count,
                "urgent_open": urgent_count,
                "resolved": resolved,
                "by_category": by_category,
                "resolve_rate": round(resolved / total, 4) if total else 0.0,
                "avg_response_minutes": round(float(avg_seconds) / 60, 1) if avg_seconds is not None else None,
            }

    @staticmethod
    def _dict(row: ServiceRequest) -> dict:
        return {
            "id": row.id,
            "park_id": row.park_id,
            "visitor_ref": row.visitor_ref,
            "category": row.category,
            "category_label": CATEGORY_LABEL.get(row.category, row.category),
            "content": row.content,
            "contact": row.contact,
            "urgent": row.urgent,
            "status": row.status,
            "status_label": STATUS_LABEL.get(row.status, row.status),
            "reply": row.reply,
            "handled_by": row.handled_by,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "replied_at": row.replied_at.isoformat() if row.replied_at else None,
        }


class ReviewService:
    """评价与景区回复。"""

    def create(
        self,
        *,
        park_id: str,
        order_id: str | None,
        visitor_ref: str,
        rating: int,
        content: str = "",
        tags: list[str] | None = None,
    ) -> tuple[dict | None, str | None]:
        rating = int(rating)
        if rating < 1 or rating > 5:
            return None, "评分需在 1~5 之间"

        with SessionLocal() as db:
            # 一单一评：重复提交应更新而不是堆积，否则同一趟行程能刷出多份评价
            existing = None
            if order_id:
                existing = db.scalars(select(Review).where(Review.order_id == order_id)).first()

            if existing is not None:
                existing.rating = rating
                existing.content = content.strip()
                existing.tags = list(tags or [])
                db.commit()
                db.refresh(existing)
                return self._dict(existing), None

            row = Review(
                id=uuid.uuid4().hex,
                park_id=park_id,
                order_id=order_id,
                visitor_ref=visitor_ref or "",
                rating=rating,
                content=content.strip(),
                tags=list(tags or []),
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return self._dict(row), None

    def list(self, *, park_id: str | None = None, limit: int = 50) -> list[dict]:
        with SessionLocal() as db:
            stmt = select(Review)
            if park_id:
                stmt = stmt.where(Review.park_id == park_id)
            rows = db.scalars(stmt.order_by(Review.created_at.desc()).limit(limit)).all()
            return [self._dict(row) for row in rows]

    def reply(self, review_id: str, reply: str) -> dict | None:
        with SessionLocal() as db:
            row = db.get(Review, review_id)
            if row is None:
                return None
            row.reply = reply.strip()
            row.replied_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(row)
            return self._dict(row)

    def summary(self, park_id: str | None = None) -> dict:
        """评分汇总：均分 + 分布。分布比均分更有用——
        4.2 分可能来自"多数 5 分加少量 1 分"，也可能是"全是 4 分"，对策完全不同。"""
        with SessionLocal() as db:
            stmt = select(Review.rating)
            if park_id:
                stmt = stmt.where(Review.park_id == park_id)
            ratings = list(db.scalars(stmt).all())

            distribution = {str(score): 0 for score in range(5, 0, -1)}
            for score in ratings:
                distribution[str(score)] = distribution.get(str(score), 0) + 1

            return {
                "total": len(ratings),
                "average": round(sum(ratings) / len(ratings), 2) if ratings else 0.0,
                "distribution": distribution,
            }

    @staticmethod
    def _dict(row: Review) -> dict:
        return {
            "id": row.id,
            "park_id": row.park_id,
            "order_id": row.order_id,
            "visitor_ref": row.visitor_ref,
            "rating": row.rating,
            "content": row.content,
            "tags": list(row.tags or []),
            "reply": row.reply,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "replied_at": row.replied_at.isoformat() if row.replied_at else None,
        }
