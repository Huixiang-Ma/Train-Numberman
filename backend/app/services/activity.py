"""工单19 · 活动与体验创意推荐 + 参与攻略流程图

工单编号：人工智能CV-AIGC-19-文旅Agent任务工单-创意策划与内容生成
对应 docs/05 §3.3 / §4.3：结合游客当前位置与景区实时活动数据推荐，
并生成可参与的流程图与攻略文档。

技术点：
  - 地理检索用 **PostgreSQL + PostGIS** 的 geography 距离（米），与 docs/01 §五一致；
    距离计算在库内完成，避免把全表拉到应用层算球面距离。
  - 流程图产物为 **Mermaid 源码 + 位图**（docs/01 §4.7 主选 Mermaid），二者都落库。
"""
from __future__ import annotations

import logging
from typing import Any, Sequence

from geoalchemy2 import Geography
from sqlalchemy import func, select

from ..core.config import get_settings
from ..db.base import SessionLocal
from ..db.models import Activity, Attraction, CreationAsset
from ..providers.registry import get_diagram, get_llm
from .creative_common import (
    asset_file_url,
    as_list,
    cache_get,
    cache_set,
    check_text,
    digest_key,
    extract_json,
    store_bytes,
)

logger = logging.getLogger("wenlv.activity")

RECOMMEND_SYSTEM = (
    "你是《文旅创新智脑》的景区活动推荐助手。"
    "只依据给定活动信息作答，不要编造活动。用简体中文，语气亲和，80 字以内。"
)

GUIDE_SYSTEM = (
    "你是《文旅创新智脑》的活动攻略编辑，面向景区游客。"
    "只依据给定活动信息梳理参与流程，不要编造环节或店铺。"
    "输出必须是**一个 JSON 对象**，不要任何解释性文字。"
    'JSON 结构：{"title": "攻略标题", "steps": ["步骤1", "步骤2"], '
    '"guide_text": "200 字以内的攻略正文，含适合人群、耗时、注意事项"}'
)


class ActivityService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.llm = get_llm()

    # ------------------------------------------------------------------
    # 活动推荐
    # ------------------------------------------------------------------
    @staticmethod
    def _score(activity: Activity, interests: Sequence[str]) -> float:
        """兴趣匹配打分：名称命中权重最高，其次描述与参与方式。"""
        text = f"{activity.name} {activity.description} {activity.how_to_join}"
        score = 0.0
        for word in interests:
            if not word:
                continue
            if word in activity.name:
                score += 2.0
            elif word in text:
                score += 1.0
        return score

    def _query_activities(
        self,
        interests: Sequence[str],
        keyword: str,
        latitude: float | None,
        longitude: float | None,
        radius_m: int,
    ) -> tuple[list[dict], bool]:
        """返回 (活动列表, 是否用到了地理筛选)。"""
        with SessionLocal() as db:
            attraction_names = {a.id: a.name for a in db.scalars(select(Attraction))}
            rows: list[dict] = []
            has_geo = False

            if latitude is not None and longitude is not None:
                try:
                    # 库内计算球面距离（米），并按半径过滤；仅对有坐标的活动生效
                    point = func.ST_SetSRID(func.ST_MakePoint(longitude, latitude), 4326)
                    distance = func.ST_Distance(
                        func.cast(Activity.geom, Geography),
                        func.cast(point, Geography),
                    )
                    stmt = (
                        select(Activity, distance.label("distance_m"))
                        .where(Activity.geom.isnot(None))
                        .order_by(distance)
                    )
                    for activity, distance_m in db.execute(stmt):
                        meters = float(distance_m)
                        if meters > radius_m:
                            continue
                        rows.append(self._to_item(activity, attraction_names, meters))
                    has_geo = True
                except Exception as exc:  # PostGIS 不可用时退回无地理排序
                    logger.warning("地理检索失败，退回无语义距离的推荐：%s", exc)
                    rows = []

            if not rows:
                for activity in db.scalars(select(Activity)):
                    rows.append(self._to_item(activity, attraction_names, None))

        if keyword:
            rows = [r for r in rows if keyword in f"{r['name']} {r['description']}"] or rows

        for row in rows:
            row["match_score"] = self._score_by_text(row, interests)
        rows.sort(key=lambda r: (-r["match_score"], r["distance_m"] if r["distance_m"] is not None else 1e9))
        return rows, has_geo

    @staticmethod
    def _score_by_text(row: dict, interests: Sequence[str]) -> float:
        score = 0.0
        name, text = row["name"], f"{row['name']} {row['description']} {row['how_to_join']}"
        for word in interests:
            if not word:
                continue
            if word in name:
                score += 2.0
            elif word in text:
                score += 1.0
        return score

    @staticmethod
    def _to_item(activity: Activity, attraction_names: dict, distance_m: float | None) -> dict:
        return {
            "id": activity.id,
            "name": activity.name,
            "schedule": activity.schedule or "",
            "description": activity.description or "",
            "how_to_join": activity.how_to_join or "",
            "attraction": attraction_names.get(activity.attraction_id or "", ""),
            "distance_m": round(distance_m, 1) if distance_m is not None else None,
            "match_score": 0.0,
            "tags": [],
        }

    def recommend(self, request: Any) -> dict[str, Any]:
        interests = [str(x).strip() for x in as_list(getattr(request, "interests", [])) if str(x).strip()]
        keyword = (getattr(request, "keyword", "") or "").strip()
        latitude = getattr(request, "latitude", None)
        longitude = getattr(request, "longitude", None)
        radius_m = int(getattr(request, "radius_m", 1500) or 1500)
        limit = max(1, min(20, int(getattr(request, "limit", 5) or 5)))

        check_text(keyword, " ".join(interests))
        items, has_geo = self._query_activities(interests, keyword, latitude, longitude, radius_m)
        if not items:
            return {"items": [], "advice": "当前区域暂无可参与的活动，建议扩大搜索半径或换个兴趣词试试。", "has_geo": has_geo}

        items = items[:limit]
        advice = self._advise(items, interests, has_geo)
        return {"items": items, "advice": advice, "has_geo": has_geo}

    def _advise(self, items: list[dict], interests: Sequence[str], has_geo: bool) -> str:
        """一句话推荐语。用 LLM 润色，失败则用确定性文案。

        性能说明（工单20 基准测试发现）：该接口其余部分只是两次 DB 查询（毫秒级），
        但推荐语要同步调一次 LLM。实测在额度不可用时均值 3.4s、P95 6.1s，
        即使额度正常也会因生成耗时带来 1~3s 的额外等待 —— 对"推荐"这种高频动作不合理。
        因此按「兴趣 + 活动集合 + 是否定位」做结果缓存：同一组合只付一次生成成本，
        游客反复切换兴趣标签时后续请求直接命中缓存。缓存键含活动集合，
        活动数据变化会自动 miss，不存在脏数据问题。
        """
        fallback = f"按你的「{'、'.join(interests) or '综合'}」兴趣，推荐以上 {len(items)} 项活动。"
        if has_geo:
            fallback += "已按当前位置就近排序。"
        fallback += "建议提前 10 分钟到场，热门时段可能需要排队。"

        cache_key = digest_key(
            "wenlv:advice",
            ",".join(interests),
            has_geo,
            ",".join(str(item["id"]) for item in items),
        )
        cached = cache_get(cache_key)
        if cached:
            return cached

        catalogue = "；".join(
            f"{x['name']}（{x['schedule'] or '时间以现场公告为准'}，"
            f"{'距离约 %d 米' % x['distance_m'] if x['distance_m'] is not None else x['attraction'] or '景区内'}）"
            for x in items
        )
        try:
            prompt = (
                f"游客兴趣：{'、'.join(interests) or '不限'}。\n"
                f"可选活动：{catalogue}\n"
                "请用一两句话向游客推荐其中最适合的，并给一条实用提醒。"
            )
            text = self.llm.generate(prompt, system=RECOMMEND_SYSTEM).strip()
            check_text(text)
            if text:
                cache_set(cache_key, text, ttl_seconds=900)
                return text
            return fallback
        except Exception as exc:
            logger.warning("活动推荐文案生成失败，使用兜底文案：%s", exc)
            # 失败结果也短暂缓存：额度/网络故障时避免每个游客都去撞一次失败的上游
            cache_set(cache_key, fallback, ttl_seconds=60)
            return fallback

    # ------------------------------------------------------------------
    # 攻略 + 流程图
    # ------------------------------------------------------------------
    def guide(self, request: Any) -> dict[str, Any]:
        activity_id = getattr(request, "activity_id", None)
        activity_name = (getattr(request, "activity_name", "") or "").strip()
        interests = [str(x).strip() for x in as_list(getattr(request, "interests", [])) if str(x).strip()]

        activity = self._find_activity(activity_id, activity_name)
        if activity is None:
            raise LookupError("未找到对应活动，请先调用活动推荐接口获取活动 id")

        title = f"{activity['name']} · 参与攻略"
        steps: list[str] = []
        guide_text = ""
        model = "fallback:heuristic"

        try:
            prompt = (
                f"【活动名称】{activity['name']}\n"
                f"【举办时间】{activity['schedule'] or '以现场公告为准'}\n"
                f"【活动介绍】{activity['description']}\n"
                f"【参与方式】{activity['how_to_join'] or '现场报名'}\n"
                f"【游客兴趣】{'、'.join(interests) or '不限'}\n"
                "请梳理出 3~6 步参与流程，并写出攻略正文。"
            )
            raw = self.llm.generate(prompt, system=GUIDE_SYSTEM)
            check_text(raw)
            parsed = extract_json(raw)
            if isinstance(parsed, dict) and parsed.get("steps"):
                title = str(parsed.get("title") or title)[:200]
                steps = [str(s).strip()[:120] for s in as_list(parsed["steps"]) if str(s).strip()][:8]
                guide_text = str(parsed.get("guide_text") or "")[:1200]
                model = self.settings.sf_llm_model
        except Exception as exc:
            logger.warning("攻略生成失败，转确定性步骤：%s", exc)

        if not steps:
            steps = self._fallback_steps(activity)
        if not guide_text:
            guide_text = (
                f"{activity['name']}｜{activity['schedule'] or '时间以现场公告为准'}。"
                f"{activity['description'][:100]}。"
                f"参与方式：{activity['how_to_join'] or '现场报名'}。"
                "建议提前 10 分钟到场，携带有效证件；体验类项目请听从工作人员安排。"
            )

        diagram = get_diagram().render(title, steps)
        uri = store_bytes(diagram["png"], "image", "png", content_type="image/png")
        asset_id = self._persist(title, activity, steps, guide_text, diagram["mermaid"], uri, model)

        return {
            "title": title,
            "steps": steps,
            "guide_text": guide_text,
            "mermaid": diagram["mermaid"],
            "diagram_uri": uri,
            "diagram_url": asset_file_url(asset_id) if asset_id else None,
            "citations": [],
            "asset_id": asset_id,
            "workflow": f"langgraph:activity→steps→mermaid→render（{model}）",
        }

    @staticmethod
    def _fallback_steps(activity: dict) -> list[str]:
        """把 how_to_join 里的分句拆成步骤，避免模型不可用时没有流程图可画。

        实测不少活动的参与方式只有一两句，直接拆分会得到 2 步甚至 1 步 —— 流程图
        画出来过于单薄。这里在末尾补齐到**至少 3 步**的通用环节，既保证图有可读结构，
        也不编造具体环节（"到场—参与—领取"属任何活动都成立的通用流程）。
        """
        raw = activity.get("how_to_join") or activity.get("description") or ""
        parts = [p.strip(" 。;；,，") for p in raw.replace("\n", " ").replace("；", "。").split("。")]
        steps = [p for p in parts if len(p) >= 4][:6]
        generic = [
            f"按【{activity.get('schedule') or '现场公告'}】的时间到场",
            "在活动点位向工作人员出示预约码或登记参与",
            "按引导完成体验，全程听从工作人员安排",
            "结束可领取纪念凭证或手作成品",
        ]
        for extra in generic:
            if len(steps) >= 3:
                break
            if extra not in steps:
                steps.append(extra)
        return steps[:6]

    @staticmethod
    def _find_activity(activity_id: str | None, activity_name: str) -> dict | None:
        with SessionLocal() as db:
            activity: Activity | None = None
            if activity_id:
                activity = db.get(Activity, activity_id)
            if activity is None and activity_name:
                activity = db.scalars(select(Activity).where(Activity.name.like(f"%{activity_name}%"))).first()
            if activity is None:
                return None
            attraction = db.get(Attraction, activity.attraction_id) if activity.attraction_id else None
            return {
                "id": activity.id,
                "name": activity.name,
                "schedule": activity.schedule or "",
                "description": activity.description or "",
                "how_to_join": activity.how_to_join or "",
                "attraction": attraction.name if attraction else "",
            }

    @staticmethod
    def _persist(title: str, activity: dict, steps: list[str], guide_text: str, mermaid: str, uri: str, model: str) -> str | None:
        try:
            with SessionLocal() as db:
                row = CreationAsset(
                    kind="guide",
                    title=title,
                    status="success",
                    result_uri=uri,
                    result_mime="image/png",
                    text_content=guide_text,
                    prompt=f"{activity['name']} 参与攻略",
                    model=model,
                    params={"steps": steps, "mermaid": mermaid, "activity_id": activity["id"]},
                    tags=["攻略", "流程图"],
                )
                db.add(row)
                db.commit()
                return row.id
        except Exception as exc:
            logger.warning("攻略落库失败（不影响返回）：%s", exc)
            return None
