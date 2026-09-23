"""docs/09 G5 · 数据分析与游客需求洞察（批次 6）

工单编号：人工智能CV-AIGC-16-【必选】文旅Agent任务工单-需求分析与功能设计

对应工单16 §2.1 第 4 条「通过数据分析工具精准洞察游客需求」与 docs/09 §3.2 的 G5。

两条方法论上的自律，直接影响结论可信度：
  1. **不造指标**。凡是没有真实数据源的指标（如闸口物理客流、活动点击），
     一律不显示，并在 `gaps` 里显式列出缺失原因 —— 一个编出来的折线图
     比一个空着的模块危害更大，因为它会被写进汇报材料。
  2. **口径写在返回值里**。核销率的分母、热点的算法（二元组词频而非语义聚类）、
     趋势的统计窗口，都随数据一起返回，供页面如实标注。
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select

from ..db.base import SessionLocal
from ..db.models import (
    CreationAsset,
    DigitalTicket,
    Park,
    QueryLog,
    Review,
    ServiceRequest,
    ShareLink,
    TicketOrder,
    TicketSlot,
    TicketType,
)

logger = logging.getLogger(__name__)

# 意图分类中文名。取值来自 services/dialog.py 的判定结果。
INTENT_LABEL = {
    "qa": "知识问答",
    "guide": "导览讲解",
    "itinerary": "行程策划",
    "activity": "活动推荐",
    "ticket": "票务咨询",
    "service": "服务求助",
    "chitchat": "闲聊",
    "": "未分类",
}

# 二元组停用词：这些组合在任何中文问句里都高频，统计出来只会淹没真正的热点
STOP_BIGRAMS = {
    "什么", "怎么", "可以", "请问", "一下", "哪里", "多少", "为什", "么样", "有什",
    "么好", "有哪", "哪些", "不是", "这个", "那个", "我是", "我想", "我要", "想要",
    "知道", "告诉", "介绍", "讲讲", "说说", "附近", "推荐", "适合", "需要", "有无",
}


def record_query(
    *,
    source: str,
    question: str,
    intent: str = "",
    session_id: str = "",
    lang: str = "zh",
    citations: int = 0,
    has_image: bool = False,
    has_audio: bool = False,
    latency_ms: int = 0,
) -> None:
    """记录一次游客提问。

    **任何异常都只写日志、绝不上抛**：埋点是分析用的旁路，
    它挂掉不能连带把游客的问答一起弄挂。这是本函数最重要的性质。
    """
    try:
        with SessionLocal() as db:
            db.add(
                QueryLog(
                    source=source,
                    session_id=session_id or "",
                    question=(question or "")[:2000],
                    intent=intent or "",
                    lang=lang or "zh",
                    answered=bool(citations) or bool(intent),
                    citations=int(citations),
                    has_image=bool(has_image),
                    has_audio=bool(has_audio),
                    latency_ms=int(latency_ms),
                )
            )
            db.commit()
    except Exception as exc:  # pragma: no cover - 旁路失败不影响主链路
        logger.warning("提问埋点写入失败（不影响问答）：%s", exc)


def _hot_bigrams(texts: list[str], top: int = 12) -> list[dict]:
    """中文二元组词频。

    为什么用二元组而不是"语义聚类"：项目未引入中文分词器，
    硬凑一个聚类结果会把不同问题混成一个标签，看起来高级但会误导运营。
    二元组词频是一个**可解释、可复现**的统计口径，页面会如实标注算法。
    """
    counts: Counter[str] = Counter()
    for text in texts:
        # 按非中文切段，避免跨标点拼出无意义组合
        for run in re.findall(r"[\u4e00-\u9fff]+", text or ""):
            for index in range(len(run) - 1):
                bigram = run[index : index + 2]
                if bigram not in STOP_BIGRAMS:
                    counts[bigram] += 1
    # 只保留出现 2 次以上的：出现 1 次的"热点"没有任何洞察价值
    return [{"word": word, "count": count} for word, count in counts.most_common(top) if count > 1]


class AnalyticsService:
    """经营分析与需求洞察的聚合查询。本服务**只读**（埋点写入走 record_query）。"""

    # ------------------------------------------------------------ 经营总览

    def business_overview(self, park_id: str | None = None, days: int = 30) -> dict:
        """票务、满意度、服务三条线的经营汇总，外加核销时段分布。"""
        from .service_request import ReviewService, ServiceRequestService
        from .ticket import TicketService

        with SessionLocal() as db:
            order_filter = [TicketOrder.park_id == park_id] if park_id else []

            # --- 票种销售结构：按票种而不是按类别，运营要看的是具体票种 ---
            structure_rows = db.execute(
                select(
                    TicketType.name,
                    TicketType.category,
                    func.coalesce(func.sum(TicketOrder.quantity), 0),
                    func.coalesce(func.sum(TicketOrder.amount_cents), 0),
                )
                .join(TicketOrder, TicketOrder.ticket_type_id == TicketType.id)
                .where(TicketOrder.status.in_(("paid", "checked_in")), *order_filter)
                .group_by(TicketType.name, TicketType.category)
                .order_by(func.coalesce(func.sum(TicketOrder.quantity), 0).desc())
            ).all()

            # --- 核销时段分布：这是本项目**唯一真实的入园时段数据源** ---
            # 用电子票的 checked_in_at 而不是订单的：一单多票时，游客可能分批入园
            hour_rows = db.execute(
                select(
                    func.extract("hour", DigitalTicket.checked_in_at),
                    func.count(),
                )
                .where(DigitalTicket.status == "checked_in", DigitalTicket.checked_in_at.isnot(None))
                .group_by(func.extract("hour", DigitalTicket.checked_in_at))
                .order_by(func.extract("hour", DigitalTicket.checked_in_at))
            ).all()

            # --- 近 N 天的下单趋势 ---
            since = datetime.now(timezone.utc) - timedelta(days=days)
            trend_rows = db.execute(
                select(func.date(TicketOrder.booked_at), func.count(), func.coalesce(func.sum(TicketOrder.quantity), 0))
                .where(TicketOrder.booked_at >= since)
                .group_by(func.date(TicketOrder.booked_at))
                .order_by(func.date(TicketOrder.booked_at))
            ).all()

            # --- 内容产量与传播 ---
            asset_rows = db.execute(
                select(CreationAsset.kind, func.count()).group_by(CreationAsset.kind).order_by(func.count().desc())
            ).all()
            share_total = int(db.scalar(select(func.count()).select_from(ShareLink)) or 0)
            share_visits = int(db.scalar(select(func.coalesce(func.sum(ShareLink.visits), 0))) or 0)

        ticket_stats = TicketService().stats(park_id)
        return {
            "park_id": park_id,
            "days": days,
            "ticket": ticket_stats,
            "ticket_structure": [
                {
                    "name": name,
                    "category": category,
                    "quantity": int(quantity),
                    "amount_cents": int(amount),
                    "share": round(int(quantity) / ticket_stats["tickets_sold"], 4) if ticket_stats["tickets_sold"] else 0.0,
                }
                for name, category, quantity, amount in structure_rows
            ],
            "checkin_hours": [{"hour": int(hour) if hour is not None else None, "count": int(count)} for hour, count in hour_rows],
            "order_trend": [
                {"date": str(day), "orders": int(orders), "tickets": int(tickets)}
                for day, orders, tickets in trend_rows
            ],
            "content": {
                "by_kind": [{"kind": kind, "count": int(count)} for kind, count in asset_rows],
                "total": sum(int(count) for _, count in asset_rows),
                "share_links": share_total,
                "share_visits": share_visits,
            },
            "review": ReviewService().summary(park_id),
            "service": ServiceRequestService().stats(park_id),
            "gaps": _GAPS,
        }

    def park_comparison(self, days: int = 30) -> list[dict]:
        """跨景区对比：G1 通用化的直接价值就是"能横向比"，单景区形态下没有这一栏。"""
        since = datetime.now(timezone.utc) - timedelta(days=days)
        with SessionLocal() as db:
            parks = db.scalars(select(Park).order_by(Park.name)).all()
            rows: list[dict] = []
            for park in parks:
                orders = db.execute(
                    select(
                        func.count(),
                        func.coalesce(func.sum(TicketOrder.quantity), 0),
                        func.coalesce(func.sum(TicketOrder.amount_cents), 0),
                    ).where(TicketOrder.park_id == park.id, TicketOrder.status.in_(("paid", "checked_in")))
                ).one()
                checked = int(
                    db.scalar(
                        select(func.count()).select_from(TicketOrder).where(
                            TicketOrder.park_id == park.id, TicketOrder.status == "checked_in"
                        )
                    )
                    or 0
                )
                pending_orders = int(
                    db.scalar(
                        select(func.count()).select_from(TicketOrder).where(
                            TicketOrder.park_id == park.id, TicketOrder.status == "pending"
                        )
                    )
                    or 0
                )
                avg_rating = db.scalar(select(func.avg(Review.rating)).where(Review.park_id == park.id))
                open_service = int(
                    db.scalar(
                        select(func.count()).select_from(ServiceRequest).where(
                            ServiceRequest.park_id == park.id, ServiceRequest.status == "open"
                        )
                    )
                    or 0
                )
                review_count = int(
                    db.scalar(select(func.count()).select_from(Review).where(Review.park_id == park.id)) or 0
                )
                rows.append(
                    {
                        "park_id": park.id,
                        "park_name": park.name,
                        "level": park.level,
                        "status": park.status,
                        "daily_capacity": park.daily_capacity,
                        "ticket_types": int(
                            db.scalar(
                                select(func.count()).select_from(TicketType).where(
                                    TicketType.park_id == park.id, TicketType.status == "on_sale"
                                )
                            )
                            or 0
                        ),
                        "orders": int(orders[0] or 0),
                        "orders_pending": pending_orders,
                        "tickets": int(orders[1] or 0),
                        "amount_cents": int(orders[2] or 0),
                        "orders_checked_in": checked,
                        "checkin_rate": round(checked / int(orders[0]), 4) if int(orders[0] or 0) else 0.0,
                        "reviews": review_count,
                        "rating": round(float(avg_rating), 2) if avg_rating is not None else None,
                        "service_open": open_service,
                    }
                )
            # 按销售额排序：这是运营横向比较时第一个想看的维度
            rows.sort(key=lambda item: item["amount_cents"], reverse=True)
            return rows

    # ------------------------------------------------------------ 需求洞察

    def insight(self, days: int = 30) -> dict:
        """游客需求洞察：提问量、意图分布、热点、盲区、涉及景区、多模态占比。"""
        since = datetime.now(timezone.utc) - timedelta(days=days)
        with SessionLocal() as db:
            total = int(db.scalar(select(func.count()).select_from(QueryLog)) or 0)
            recent = int(
                db.scalar(select(func.count()).select_from(QueryLog).where(QueryLog.created_at >= since)) or 0
            )

            intent_rows = db.execute(
                select(QueryLog.intent, func.count())
                .where(QueryLog.created_at >= since)
                .group_by(QueryLog.intent)
                .order_by(func.count().desc())
            ).all()

            source_rows = db.execute(
                select(QueryLog.source, func.count()).group_by(QueryLog.source).order_by(func.count().desc())
            ).all()

            trend_rows = db.execute(
                select(func.date(QueryLog.created_at), func.count())
                .where(QueryLog.created_at >= since)
                .group_by(func.date(QueryLog.created_at))
                .order_by(func.date(QueryLog.created_at))
            ).all()

            # 盲区：检索没命中（无引文）的问题，是知识库最该补的地方
            blind_rows = db.scalars(
                select(QueryLog)
                .where(QueryLog.citations == 0, QueryLog.question != "")
                .order_by(QueryLog.created_at.desc())
                .limit(20)
            ).all()

            multi_modal = int(
                db.scalar(
                    select(func.count()).select_from(QueryLog).where(
                        (QueryLog.has_image.is_(True)) | (QueryLog.has_audio.is_(True))
                    )
                )
                or 0
            )
            avg_latency = db.scalar(select(func.avg(QueryLog.latency_ms)).where(QueryLog.latency_ms > 0))

            questions = [row.question for row in db.scalars(select(QueryLog).where(QueryLog.created_at >= since)).all()]
            recent_questions = [
                {
                    "question": row.question,
                    "intent": row.intent,
                    "intent_label": INTENT_LABEL.get(row.intent or "", row.intent or "未分类"),
                    "citations": row.citations,
                    "source": row.source,
                    "has_image": row.has_image,
                    "has_audio": row.has_audio,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in db.scalars(select(QueryLog).order_by(QueryLog.created_at.desc()).limit(30)).all()
            ]

            # 问题涉及的景区：用景区名在问题文本里做匹配。
            # 这是**字符串命中**而不是语义识别，页面会如实说明口径。
            parks = db.scalars(select(Park.name)).all()
            park_hits: Counter[str] = Counter()
            for question in questions:
                for name in parks:
                    if name and name in question:
                        park_hits[name] += 1

        return {
            "days": days,
            "total": total,
            "recent": recent,
            "multimodal": multi_modal,
            "multimodal_ratio": round(multi_modal / total, 4) if total else 0.0,
            "avg_latency_ms": round(float(avg_latency), 1) if avg_latency is not None else None,
            "intents": [
                {
                    "intent": intent or "",
                    "label": INTENT_LABEL.get(intent or "", intent or "未分类"),
                    "count": int(count),
                    "share": round(int(count) / recent, 4) if recent else 0.0,
                }
                for intent, count in intent_rows
            ],
            "sources": [{"source": source, "count": int(count)} for source, count in source_rows],
            "trend": [{"date": str(day), "count": int(count)} for day, count in trend_rows],
            "hot_words": _hot_bigrams(questions),
            "hot_word_method": "中文二元组词频（未引入分词器，页面结论需结合最近提问原文判读）",
            "park_mentions": [{"park_name": name, "count": count} for name, count in park_hits.most_common(10)],
            "park_mention_method": "景区名在问题文本中的字符串命中，非语义归属",
            "blind_spots": [
                {
                    "question": row.question,
                    "intent": row.intent,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in blind_rows
            ],
            "recent_questions": recent_questions,
            "gaps": _INSIGHT_GAPS,
        }

    # ------------------------------------------------------------ 数据查询

    def dataset(self, name: str, limit: int = 200) -> dict | None:
        """结构化数据集的只读查询，供「数据查询」页做筛选与导出。

        为什么不接自然语言问数：那需要把 NL 翻成 SQL，而本项目没有该组件；
        硬做一个关键词匹配会生成**看似能跑但结果不对**的查询，运营据此决策是危险的。
        因此这里提供确定性的人工筛选，并明确标注它不解析自然语言。
        """
        limit = max(1, min(limit, 1000))
        with SessionLocal() as db:
            if name == "parks":
                rows = db.scalars(select(Park).order_by(Park.name).limit(limit)).all()
                return {
                    "name": name,
                    "label": "景区台账",
                    "columns": ["名称", "等级", "状态", "日承载", "开放时间"],
                    "rows": [
                        [row.name, row.level or "—", row.status, row.daily_capacity, row.open_hours or "—"]
                        for row in rows
                    ],
                }
            if name == "orders":
                rows = db.scalars(select(TicketOrder).order_by(TicketOrder.created_at.desc()).limit(limit)).all()
                return {
                    "name": name,
                    "label": "票务订单",
                    "columns": ["订单号", "景区", "票种", "数量", "金额(元)", "状态", "下单时间"],
                    "rows": [
                        [
                            row.order_no,
                            (db.get(Park, row.park_id).name if db.get(Park, row.park_id) else "—"),
                            (db.get(TicketType, row.ticket_type_id).name if db.get(TicketType, row.ticket_type_id) else "—"),
                            row.quantity,
                            round(row.amount_cents / 100, 2),
                            row.status,
                            row.booked_at.isoformat()[:19] if row.booked_at else "—",
                        ]
                        for row in rows
                    ],
                }
            if name == "tickets":
                rows = db.scalars(select(DigitalTicket).order_by(DigitalTicket.created_at.desc()).limit(limit)).all()
                return {
                    "name": name,
                    "label": "电子票",
                    "columns": ["票号", "所属订单", "状态", "核销闸口", "核销时间"],
                    "rows": [
                        [
                            row.code,
                            row.order_id,
                            row.status,
                            row.gate or "—",
                            row.checked_in_at.isoformat()[:19] if row.checked_in_at else "—",
                        ]
                        for row in rows
                    ],
                }
            if name == "slots":
                rows = db.scalars(
                    select(TicketSlot).order_by(TicketSlot.slot_date, TicketSlot.start_time).limit(limit)
                ).all()
                return {
                    "name": name,
                    "label": "时段库存",
                    "columns": ["票种", "日期", "时段", "库存", "已售", "余票"],
                    "rows": [
                        [
                            (db.get(TicketType, row.ticket_type_id).name if db.get(TicketType, row.ticket_type_id) else "—"),
                            row.slot_date.isoformat() if row.slot_date else "—",
                            f"{row.start_time}-{row.end_time}",
                            row.inventory,
                            row.sold,
                            max(0, row.inventory - row.sold),
                        ]
                        for row in rows
                    ],
                }
            if name == "services":
                rows = db.scalars(
                    select(ServiceRequest).order_by(ServiceRequest.created_at.desc()).limit(limit)
                ).all()
                return {
                    "name": name,
                    "label": "游客服务工单",
                    "columns": ["类型", "内容", "状态", "加急", "提交时间"],
                    "rows": [
                        [
                            row.category,
                            (row.content[:40] + "…") if len(row.content) > 40 else row.content,
                            row.status,
                            "是" if row.urgent else "否",
                            row.created_at.isoformat()[:19] if row.created_at else "—",
                        ]
                        for row in rows
                    ],
                }
            if name == "reviews":
                rows = db.scalars(select(Review).order_by(Review.created_at.desc()).limit(limit)).all()
                return {
                    "name": name,
                    "label": "游客评价",
                    "columns": ["景区", "评分", "内容", "是否有回复"],
                    "rows": [
                        [
                            (db.get(Park, row.park_id).name if db.get(Park, row.park_id) else "—"),
                            row.rating,
                            (row.content[:40] + "…") if len(row.content) > 40 else row.content,
                            "是" if row.reply else "否",
                        ]
                        for row in rows
                    ],
                }
            if name == "queries":
                rows = db.scalars(select(QueryLog).order_by(QueryLog.created_at.desc()).limit(limit)).all()
                return {
                    "name": name,
                    "label": "游客提问",
                    "columns": ["来源", "问题", "意图", "引文数", "时间"],
                    "rows": [
                        [
                            row.source,
                            (row.question[:50] + "…") if len(row.question) > 50 else row.question,
                            row.intent or "—",
                            row.citations,
                            row.created_at.isoformat()[:19] if row.created_at else "—",
                        ]
                        for row in rows
                    ],
                }
            return None

    def datasets(self) -> list[dict]:
        return [
            {"name": "parks", "label": "景区台账"},
            {"name": "orders", "label": "票务订单"},
            {"name": "tickets", "label": "电子票"},
            {"name": "slots", "label": "时段库存"},
            {"name": "services", "label": "游客服务工单"},
            {"name": "reviews", "label": "游客评价"},
            {"name": "queries", "label": "游客提问"},
        ]


# 缺失数据源清单：随分析结果一起返回，页面据此如实标注而不是留白
_GAPS = [
    {
        "item": "闸口物理客流",
        "reason": "闸机/客流传感器未接入，本项目只有电子票核销时间。"
                  "「核销时段分布」可作入园时段的代理指标，但不等于真实客流（免票儿童、旅游团通道不计入）。",
    },
    {
        "item": "票务收入对账",
        "reason": "支付为占位实现（docs/09 §3.2），金额字段是下单金额而非到账金额，不能用于财务对账。",
    },
]

_INSIGHT_GAPS = [
    {
        "item": "问题语义聚类",
        "reason": "未引入中文分词与向量聚类组件，热点用二元组词频给出；"
                  "同一主题的不同问法不会自动合并，需结合「最近提问」原文判读。",
    },
    {
        "item": "活动与内容点击",
        "reason": "前端未埋点，无法回答「推荐了什么被点了」。属于前端埋点缺失，不是后端能力缺失。",
    },
    {
        "item": "埋点起始时间",
        "reason": "query_log 自批次 6 起才开始记录，在此之前的历史问答没有数据，"
                  "刚部署时趋势图会是空的，这不是故障。",
    },
]
