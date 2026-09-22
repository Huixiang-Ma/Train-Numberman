"""工单17 · 目的地 / 景区读服务（docs/09 G1：通用化三层归属）

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成

定位：只读。给游客端的「发现 / 景区详情」与管理端的「景区管理」供数。
不承担任何写入，写入由 scripts/seed_parks.py 与后续的管理端接口负责。
"""
from __future__ import annotations

import logging

from geoalchemy2 import Geography
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import JSONB

from ..db.base import SessionLocal
from ..db.models import Activity, Attraction, Destination, Park

logger = logging.getLogger(__name__)


class ParkService:
    """目的地与景区的查询服务。"""

    # ---------------- 目的地 ----------------
    def destinations(self) -> list[dict]:
        """目的地列表，附带景区数量与代表标签，供游客端首屏卡片使用。"""
        with SessionLocal() as db:
            rows = db.scalars(select(Destination).order_by(Destination.name)).all()
            counts = dict(
                db.execute(
                    select(Park.destination_id, func.count()).group_by(Park.destination_id)
                ).all()
            )
            return [self._destination_dict(row, int(counts.get(row.id) or 0)) for row in rows]

    # ---------------- 景区 ----------------
    def parks(
        self,
        destination_id: str | None = None,
        keyword: str | None = None,
        tag: str | None = None,
        near_lat: float | None = None,
        near_lon: float | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """景区列表。

        支持四种筛选：目的地、关键词（名称/简介）、标签、以及按距离。
        距离排序与 activity 服务保持同一写法（球面距离 + Geography 转换），
        并在 PostGIS 不可用时退回无地理排序，不让整个列表失败。
        """
        with SessionLocal() as db:
            stmt = select(Park)
            if destination_id:
                stmt = stmt.where(Park.destination_id == destination_id)
            if keyword:
                like = f"%{keyword.strip()}%"
                # 必须用 sqlalchemy.or_（布尔运算符）；func.or_ 会被渲染成函数调用 or(...)，
                # PostgreSQL 无此函数，报 SyntaxError。
                stmt = stmt.where(or_(Park.name.ilike(like), Park.summary.ilike(like)))
            if tag:
                # tags 列是 json（不是 jsonb），而 `@>` 包含运算符只有 jsonb 支持；
                # SQLAlchemy 的 contains() 在 json 上会退化成字符串 LIKE，触发
                # "operator does not exist: json ~~ text"。这里显式转成 jsonb 做包含判断，
                # 从而在不改动既有列类型的前提下得到精确的数组元素匹配。
                stmt = stmt.where(func.cast(Park.tags, JSONB).contains([tag]))

            rows: list[tuple[Park, float | None]] = []
            used_geo = False
            if near_lat is not None and near_lon is not None:
                try:
                    point = func.ST_SetSRID(func.ST_MakePoint(near_lon, near_lat), 4326)
                    distance = func.ST_Distance(
                        func.cast(Park.geom, Geography),
                        func.cast(point, Geography),
                    )
                    geo_stmt = (
                        stmt.where(Park.geom.isnot(None)).add_columns(distance.label("distance_m")).order_by(distance)
                    )
                    rows = [(row, float(dist)) for row, dist in db.execute(geo_stmt)]
                    used_geo = True
                except Exception as exc:  # PostGIS 不可用时退回普通排序
                    logger.warning("景区地理检索失败，退回无距离排序：%s", exc)
                    rows = []
            if not used_geo:
                rows = [(row, None) for row in db.scalars(stmt.order_by(Park.name).limit(limit)).all()]

            park_ids = [row.id for row, _ in rows]
            attraction_counts = dict(
                db.execute(
                    select(Attraction.park_id, func.count())
                    .where(Attraction.park_id.in_(park_ids) if park_ids else False)
                    .group_by(Attraction.park_id)
                ).all()
            )
            destination_names = dict(db.execute(select(Destination.id, Destination.name)).all())

            return [
                self._park_dict(row, destination_names.get(row.destination_id), int(attraction_counts.get(row.id) or 0), distance)
                for row, distance in rows[:limit]
            ]

    def park(self, park_id: str) -> dict | None:
        """景区详情：景区本体 + 景点列表 + 该景区下可参与的活动。"""
        with SessionLocal() as db:
            row = db.get(Park, park_id)
            if row is None:
                return None

            attractions = db.scalars(
                select(Attraction).where(Attraction.park_id == park_id).order_by(Attraction.name)
            ).all()
            attraction_ids = [item.id for item in attractions]
            activities = (
                db.scalars(
                    select(Activity)
                    .where(Activity.attraction_id.in_(attraction_ids))
                    .order_by(Activity.name)
                ).all()
                if attraction_ids
                else []
            )
            destination = db.get(Destination, row.destination_id) if row.destination_id else None

            data = self._park_dict(row, destination.name if destination else None, len(attractions), None)
            data["destination"] = (
                {"id": destination.id, "name": destination.name, "region": destination.region}
                if destination
                else None
            )
            data["attractions"] = [self._attraction_dict(item) for item in attractions]
            data["activities"] = [self._activity_dict(item) for item in activities]
            return data

    # ---------------- 行 → dict ----------------
    @staticmethod
    def _destination_dict(row: Destination, park_count: int) -> dict:
        return {
            "id": row.id,
            "name": row.name,
            "region": row.region,
            "summary": row.summary,
            "description": row.description,
            "tags": list(row.tags or []),
            "park_count": park_count,
        }

    @staticmethod
    def _park_dict(row: Park, destination_name: str | None, attraction_count: int, distance_m: float | None) -> dict:
        return {
            "id": row.id,
            "name": row.name,
            "destination_id": row.destination_id,
            "destination_name": destination_name,
            "summary": row.summary,
            "description": row.description,
            "open_hours": row.open_hours,
            "status": row.status,
            "daily_capacity": row.daily_capacity,
            "level": row.level,
            "ticket_notice": row.ticket_notice,
            "cover_uri": row.cover_uri,
            "tags": list(row.tags or []),
            "attraction_count": attraction_count,
            "distance_m": round(distance_m, 1) if distance_m is not None else None,
        }

    @staticmethod
    def _attraction_dict(row: Attraction) -> dict:
        return {
            "id": row.id,
            "name": row.name,
            "summary": row.summary,
            "description": row.description,
            "open_hours": row.open_hours,
            "tags": list(row.tags or []),
            "park_id": row.park_id,
        }

    @staticmethod
    def _activity_dict(row: Activity) -> dict:
        return {
            "id": row.id,
            "name": row.name,
            "schedule": row.schedule,
            "description": row.description,
            "how_to_join": row.how_to_join,
            "attraction_id": row.attraction_id,
        }
