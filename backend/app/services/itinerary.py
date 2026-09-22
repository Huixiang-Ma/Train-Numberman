"""工单19 · 个性化旅游线路与活动创意生成

工单编号：人工智能CV-AIGC-19-文旅Agent任务工单-创意策划与内容生成
对应 docs/05 §3.1 / §4.1：结合景区知识库与实时数据，按兴趣、主题、时间生成专属行程。

两条设计约束：
  1. **分站必须来自真实景点/活动数据**。候选先由关系库（PostgreSQL）与知识库（Milvus）
     取出并交给模型编排，模型只负责"排序、配时、给理由"，不让它凭空造景点。
  2. **必须能在模型不可用时降级**。生成式链路任一环失败（网络、额度、输出不合法），
     就退回确定性排程：按兴趣重合度排序候选、按时长切片配时。接口始终可用。
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any, Sequence

from sqlalchemy import select

from ..core.config import get_settings
from ..db.base import SessionLocal
from ..db.models import Activity, Attraction, ItineraryPlan
from ..providers.base import Hit
from ..providers.registry import get_llm
from .creative_common import as_list, check_text, extract_json

logger = logging.getLogger("wenlv.itinerary")

SYSTEM_PROMPT = (
    "你是《文旅创新智脑》的行程策划师，面向景区游客做个性化线路策划。"
    "只能使用【候选景点】【候选活动】【参考资料】里出现过的名称，绝不编造景点或商铺。"
    "输出必须是**一个 JSON 对象**，且不要输出任何解释性文字。"
    "JSON 结构："
    '{"title": "行程标题", "summary": "一句话概括", '
    '"stops": [{"name": "景点名", "start_time": "09:00", "duration": "1 小时", '
    '"kind": "sight|food|activity|rest|photo", "reason": "为什么安排在这里（结合兴趣）", '
    '"tips": "实用提示"}]}'
)

# 时长档位 → 分站数上限（半日游安排过多站点在体验上是负分）
DURATION_STOPS = {"半日": 4, "一日": 6, "两日": 10}
PACE_FACTOR = {"紧凑": 1.25, "适中": 1.0, "舒缓": 0.75}


class ItineraryService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.llm = get_llm()

    # ------------------------------------------------------------------
    # 候选获取
    # ------------------------------------------------------------------
    def _candidates(self, interests: Sequence[str], limit: int) -> tuple[list[dict], list[dict]]:
        """从关系库读取候选景点与活动，并按兴趣标签重合度排序。

        用应用层排序而不是 SQL 的 JSON 包含查询：数据量小，且 tags 使用 JSON 列，
        不同数据库的包含运算符不一致，应用层排序可移植且便于加权。
        """
        wanted = {x.strip() for x in interests if x and x.strip()}

        def overlap(tags: Iterable) -> int:
            return len(wanted & {str(t) for t in (tags or [])})

        name_hits = " ".join(wanted)

        with SessionLocal() as db:
            attractions = list(db.scalars(select(Attraction)))
            activities = list(db.scalars(select(Activity)))

        for item in attractions:
            item.__dict__["_score"] = overlap(item.tags)
        attractions.sort(key=lambda a: (a.__dict__.get("_score", 0), len(a.summary or "")), reverse=True)

        def activity_score(act: Activity) -> float:
            text = f"{act.name} {act.description} {act.how_to_join}"
            keyword = sum(1 for word in wanted if word and word in text)
            return keyword + (0.5 if name_hits and name_hits in text else 0.0)

        activities.sort(key=activity_score, reverse=True)

        return (
            [
                {
                    "name": a.name,
                    "summary": (a.summary or a.description or "")[:120],
                    "tags": list(a.tags or []),
                    "open_hours": a.open_hours or "",
                }
                for a in attractions[:limit]
            ],
            [
                {
                    "name": act.name,
                    "schedule": act.schedule or "",
                    "description": (act.description or "")[:120],
                    "how_to_join": act.how_to_join or "",
                }
                for act in activities[:limit]
            ],
        )

    @staticmethod
    def _knowledge(query: str, top_k: int) -> list[Hit]:
        """知识库检索（用于引用来源）。失败时返回空，不阻断策划。"""
        try:
            from .retrieval import RetrievalService

            return RetrievalService().text_to_text(query, top_k=top_k)
        except Exception as exc:  # 向量库/嵌入服务不可用时降级为无引用
            logger.warning("线路策划检索失败，降级为无引用：%s", exc)
            return []

    # ------------------------------------------------------------------
    # 提示词
    # ------------------------------------------------------------------
    @staticmethod
    def _build_prompt(payload: dict[str, Any], attractions: list[dict], activities: list[dict], hits: Sequence[Hit]) -> str:
        lines = [
            f"【游客画像】兴趣：{'、'.join(payload['interests']) or '不限'}；"
            f"主题：{payload['theme']}；可用时长：{payload['duration']}；"
            f"同行：{payload['companions']}；节奏：{payload['pace']}；出发地：{payload['start_point']}",
            f"【分站数量】请安排 {payload['stop_limit']} 个分站，按时间先后排列",
            "【候选景点】" + ("；".join(f"{a['name']}（{'/'.join(a['tags']) or '综合'}，{a['summary']}）" for a in attractions) or "（无）"),
            "【候选活动】" + ("；".join(f"{x['name']}（{x['schedule']}，{x['description']}）" for x in activities) or "（无）"),
        ]
        if hits:
            context = "\n".join(
                f"[{i}] 《{h.chunk.title}》{h.chunk.content.strip()[:160]}" for i, h in enumerate(hits, start=1)
            )
            lines.append(f"【参考资料】\n{context}")
        lines.append(
            "请据此输出 JSON 行程。要求：分站名称必须取自候选景点或候选活动；"
            "每个分站给出 start_time、duration、kind、结合游客兴趣的 reason 与实用 tips；"
            "美食类分站可安排在参观之间。"
        )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 确定性兜底排程
    # ------------------------------------------------------------------
    @staticmethod
    def _fallback_stops(attractions: list[dict], activities: list[dict], stop_limit: int, duration: str) -> list[dict]:
        """模型不可用时的降级排程：按兴趣重合度顺序切片，按时长配时。

        这一步保证接口在任何情况下都能返回结构完整、内容真实的行程，
        而不是抛错或返回空列表。
        """
        start_hour = 9 if duration != "半日" else 8
        minutes = 30
        # 交错的参观/活动节奏：每两个景点之间插一个活动，比"连着看完再动手"更符合真实游览体验
        pool: list[dict] = []
        for index in range(max(len(attractions), len(activities))):
            if index < len(attractions):
                pool.append({"name": attractions[index]["name"], "summary": attractions[index]["summary"],
                             "tags": attractions[index].get("tags") or [], "kind": "sight"})
            if index < len(activities):
                pool.append({"name": activities[index]["name"], "summary": activities[index]["description"],
                             "tags": activities[index].get("tags") or [], "kind": "activity"})
        stops: list[dict] = []
        for item in pool[:stop_limit]:
            total = start_hour * 60 + minutes
            stops.append(
                {
                    "name": item["name"],
                    "start_time": f"{total // 60:02d}:{total % 60:02d}",
                    "duration": "1 小时" if item["kind"] == "sight" else "45 分钟",
                    "kind": item["kind"],
                    "reason": f"契合你的「{'、'.join(item['tags'][:2]) or '综合'}」兴趣",
                    "tips": item["summary"][:60],
                    "tags": item["tags"],
                }
            )
            minutes += 90 if item["kind"] == "sight" else 60
        return stops

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------
    def plan(self, request: Any) -> dict[str, Any]:
        interests = [x.strip() for x in as_list(getattr(request, "interests", [])) if str(x).strip()]
        duration = getattr(request, "duration", "半日") or "半日"
        pace = getattr(request, "pace", "适中") or "适中"
        theme = getattr(request, "theme", "") or "文化深度游"
        companions = getattr(request, "companions", "独自") or "独自"
        start_point = getattr(request, "start_point", "景区主入口") or "景区主入口"

        check_text(theme, " ".join(interests), companions)

        base = DURATION_STOPS.get(duration, 4)
        stop_limit = max(3, min(12, int(round(base * PACE_FACTOR.get(pace, 1.0)))))

        attractions, activities = self._candidates(interests, limit=14)
        query = f"{theme} {' '.join(interests)} 景点 活动".strip()
        hits = self._knowledge(query, self.settings.rerank_top_n * 2)

        payload = {
            "interests": interests,
            "theme": theme,
            "duration": duration,
            "companions": companions,
            "pace": pace,
            "start_point": start_point,
            "stop_limit": stop_limit,
        }

        title = f"{theme}·{duration}"
        summary = ""
        stops: list[dict] = []
        model = "fallback:heuristic"

        try:
            raw = self.llm.generate(self._build_prompt(payload, attractions, activities, hits), system=SYSTEM_PROMPT)
            check_text(raw)
            parsed = extract_json(raw)
            if isinstance(parsed, dict) and isinstance(parsed.get("stops"), list) and parsed["stops"]:
                title = str(parsed.get("title") or title)[:200]
                summary = str(parsed.get("summary") or "")[:400]
                stops = [
                    {
                        "name": str(s.get("name") or "").strip()[:128],
                        "start_time": str(s.get("start_time") or "").strip()[:16],
                        "duration": str(s.get("duration") or "").strip()[:32],
                        "kind": str(s.get("kind") or "sight").strip()[:16],
                        "reason": str(s.get("reason") or "").strip()[:200],
                        "tips": str(s.get("tips") or "").strip()[:200],
                    }
                    for s in parsed["stops"]
                    if isinstance(s, dict) and str(s.get("name") or "").strip()
                ][:stop_limit]
                model = f"{self.settings.sf_llm_model}"
            else:
                logger.warning("行程策划返回内容不是可解析的 JSON，转确定性排程")
        except Exception as exc:
            logger.warning("行程策划调用模型失败，转确定性排程：%s", exc)

        if not stops:
            stops = self._fallback_stops(attractions, activities, stop_limit, duration)

        for index, stop in enumerate(stops):
            stop["index"] = index + 1
            stop.setdefault("tags", [])

        citations = [
            {
                "kb_id": h.chunk.id,
                "title": h.chunk.title,
                "source": h.chunk.source,
                "score": round(float(h.rerank_score if h.rerank_score is not None else h.score), 4),
            }
            for h in hits
        ]

        route = self._route_text(title, summary, stops, payload)
        plan_id = self._persist(payload, title, summary, stops, citations, model, route)

        return {
            "plan_id": plan_id,
            "title": title,
            "summary": summary or f"为「{'、'.join(interests) or '综合'}」兴趣定制的{duration}行程",
            "stops": stops,
            "citations": citations,
            "route_text": route,
            "workflow": f"langgraph:profile→retrieve→plan→format（{model}）",
        }

    # ------------------------------------------------------------------
    @staticmethod
    def _route_text(title: str, summary: str, stops: list[dict], payload: dict) -> str:
        """行程单纯文本：可直接下载、分享或复制到聊天里。"""
        lines = [
            f"《{title}》",
            f"主题：{payload['theme']}　时长：{payload['duration']}　节奏：{payload['pace']}　同行：{payload['companions']}",
            f"出发地：{payload['start_point']}",
        ]
        if summary:
            lines.append(summary)
        lines.append("-" * 28)
        for stop in stops:
            time_text = f"{stop['start_time']} " if stop.get("start_time") else ""
            lines.append(f"{stop['index']}. {time_text}{stop['name']}（{stop.get('duration') or '—'}）")
            if stop.get("reason"):
                lines.append(f"   为什么：{stop['reason']}")
            if stop.get("tips"):
                lines.append(f"   提示：{stop['tips']}")
        lines.append("-" * 28)
        lines.append("由《文旅创新智脑》生成，请以景区实时公告为准。")
        return "\n".join(lines)

    def _persist(
        self,
        payload: dict,
        title: str,
        summary: str,
        stops: list[dict],
        citations: list[dict],
        model: str,
        route: str,
    ) -> str | None:
        """落库保存，便于「我的创作」回看与二次编辑。失败不阻断返回。"""
        try:
            with SessionLocal() as db:
                row = ItineraryPlan(
                    session_id=payload.get("session_id"),
                    title=title,
                    summary=summary,
                    interests=payload["interests"],
                    theme=payload["theme"],
                    duration=payload["duration"],
                    companions=payload["companions"],
                    start_point=payload["start_point"],
                    stops=stops,
                    citations=citations,
                    model=model,
                    raw=route,
                )
                db.add(row)
                db.commit()
                return row.id
        except Exception as exc:
            logger.warning("行程落库失败（不影响返回）：%s", exc)
            return None
