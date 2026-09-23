"""工单18 · Agent 调度与多轮对话服务（LangGraph 编排）

工单编号：人工智能CV-AIGC-18-文旅Agent任务工单-智能导览与互动体验
职责（docs/04 §4.2 / §4.5）：统一接收多模态输入 → 意图识别 → 任务分发 → 生成 → 数字人驱动。
知识检索与生成复用阶段二（工单17）能力，不重复实现。

流程（LangGraph）：
  normalize（ASR + 环境感知）→ route（意图识别）→ retrieve（多模态检索）
  → generate（Qwen 生成）→ respond（会话落库 + 数字人驱动）
"""
from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from ..core.config import get_settings
from ..providers.registry import get_asr
from ..providers.vision_tasks import GESTURE_ACTIONS
from .avatar import EXPRESSION_TO_EMOTION, AvatarService
from .generation import GenerationService
from .perception import PerceptionService
from .retrieval import RetrievalService
from .session import SessionService

logger = logging.getLogger(__name__)

INTENT_RULES: list[tuple[str, list[str]]] = [
    ("互动", ["你好", "挥手", "打招呼", "点赞", "hello", "hi", "比心"]),
    ("识物", ["这是什么", "识别", "看看", "拍", "照片", "图片", "认一下", "什么东西"]),
    ("寻路", ["路线", "怎么走", "地图", "导航", "打卡", "动线", "怎么玩"]),
    ("活动", ["活动", "体验", "表演", "非遗", "节令", "场次"]),
    ("美食", ["美食", "吃", "餐厅", "小吃"]),
]

GREETING_FALLBACK = "你好，我是文旅数字人。可以拍照识物、语音提问，也可以让我为你规划路线。"


class DialogState(TypedDict, total=False):
    session_id: str
    lang: str
    text: str
    image: bytes | None
    audio: bytes | None
    audio_mime: str
    with_avatar: bool
    with_perception: bool
    session_turns: int
    asr_text: str
    # 语音转写失败时的原因（空串表示正常）。与 avatar.degraded 同一套约定：
    # 上游不可用要**降级并如实说明**，而不是让整个对话失败。
    asr_degraded: str
    question: str
    perception: dict[str, Any] | None
    intent: str
    hits: list[Any]
    ocr_text: str
    answer: str
    avatar: dict[str, Any] | None


# --------------------------------------------------------------------------
# 节点
# --------------------------------------------------------------------------
def normalize_node(state: DialogState) -> DialogState:
    """语音转文本 + 图像环境感知 + 组合问题。"""
    asr_text = ""
    asr_degraded = ""
    audio = state.get("audio")
    if audio:
        try:
            asr_text = get_asr().transcribe(audio, mime=state.get("audio_mime") or "audio/wav")
        except Exception as exc:
            # 上游 ASR 不可用（额度耗尽、网络异常、服务故障）时**必须降级而不是抛出**。
            # 原先这条链会把 402/超时直接变成整个 /dialog/multimodal 的 500，
            # 于是"图片识别 + 文本问答"这些完全正常的部分也一起不可用 ——
            # 而同一份代码里 TTS 失败已经做了降级，两处行为不一致本身就是缺陷。
            logger.warning("语音转写失败，降级为纯文本对话：%s", exc)
            asr_degraded = _degrade_reason(exc)

    perception_payload: dict[str, Any] | None = None
    image = state.get("image")
    if image and state.get("with_perception", True):
        service = PerceptionService()
        result = service.analyze(image, with_detection=True, with_classify=False, with_segments=False)
        perception_payload = service.to_payload(result)
        perception_payload["suggestion"] = service.suggest(result)

    question = " ".join(part for part in [state.get("text"), asr_text] if part).strip()
    return {
        "asr_text": asr_text,
        "asr_degraded": asr_degraded,
        "question": question,
        "perception": perception_payload,
    }


def _degrade_reason(exc: Exception) -> str:
    """把上游异常翻成运营与游客都能看懂的一句话。

    不直接透出原始异常：`Client error '402 Payment Required' for url ...`
    对游客没有意义，而"语音识别服务额度不足"才是可行动的信息。
    """
    text = str(exc)
    if "402" in text or "Payment Required" in text:
        return "语音识别服务额度不足，本次已按文字对话处理"
    if "401" in text or "403" in text:
        return "语音识别服务鉴权失败，本次已按文字对话处理"
    if "timeout" in text.lower() or "timed out" in text.lower():
        return "语音识别服务响应超时，本次已按文字对话处理"
    return "语音识别服务暂时不可用，本次已按文字对话处理"


def route_node(state: DialogState) -> DialogState:
    """意图识别。"""
    text = (state.get("question") or "").lower()
    intent = "知识"
    for name, keywords in INTENT_RULES:
        if any(keyword in text for keyword in keywords):
            intent = name
            break
    else:
        if state.get("image"):
            intent = "识物"
    return {"intent": intent}


def retrieve_node(state: DialogState) -> DialogState:
    """多模态检索：图片走以图搜文，互动意图跳过检索，其余走以文搜文。"""
    settings = get_settings()
    service = RetrievalService()
    image = state.get("image")

    if image:
        result = service.image_search(image, top_k=settings.top_k, target="text")
        return {"hits": result["hits"], "ocr_text": result["ocr_text"]}

    question = state.get("question") or ""
    if state.get("intent") == "互动" and not question:
        return {"hits": [], "ocr_text": ""}
    return {"hits": service.text_to_text(question, top_k=settings.top_k), "ocr_text": ""}


def generate_node(state: DialogState) -> DialogState:
    """生成回答：互动意图使用预设话术，其余走 Qwen 检索增强生成。"""
    hits = state.get("hits") or []
    intent = state.get("intent")

    if not hits and intent == "互动":
        return {"answer": GREETING_FALLBACK}

    if not hits and state.get("image"):
        question = state.get("question") or state.get("ocr_text") or "请讲解这张图片"
        return {"answer": GenerationService().generate(question, [], lang=state.get("lang", "zh"))}

    question = state.get("question") or state.get("ocr_text") or "请讲解图片内容"
    return {"answer": GenerationService().generate(question, hits, lang=state.get("lang", "zh"))}


def respond_node(state: DialogState) -> DialogState:
    """会话落库 + 数字人驱动参数。"""
    service = SessionService()
    session = service.get_or_create(state.get("session_id"), lang=state.get("lang", "zh"))

    question = state.get("question") or "（多模态输入）"
    answer = state.get("answer") or ""
    service.append(session, "user", question, intent=state.get("intent"))
    service.append(session, "assistant", answer, intent=state.get("intent"))

    avatar_payload: dict[str, Any] | None = None
    if state.get("with_avatar", True) and answer:
        expression = (state.get("perception") or {}).get("expression") or {}
        emotion = EXPRESSION_TO_EMOTION.get(expression.get("name"), "calm")
        motion = "explain"
        suggestion = (state.get("perception") or {}).get("suggestion")
        if suggestion and suggestion.get("motion") in {"wave", "nod", "point"}:
            motion = suggestion["motion"]
            emotion = "cheerful" if suggestion.get("action") == "greet" else "curious"
        avatar_payload = AvatarService().drive(answer, lang=state.get("lang", "zh"), emotion=emotion, motion=motion)

    return {"session_id": session.id, "avatar": avatar_payload, "session_turns": len(session.turns)}


def build_dialog_graph():
    graph = StateGraph(DialogState)
    graph.add_node("normalize", normalize_node)
    graph.add_node("route", route_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("generate", generate_node)
    graph.add_node("respond", respond_node)
    graph.set_entry_point("normalize")
    graph.add_edge("normalize", "route")
    graph.add_edge("route", "retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", "respond")
    graph.add_edge("respond", END)
    return graph.compile()


_GRAPH = None


def get_dialog_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_dialog_graph()
    return _GRAPH


def run_dialog(
    session_id: str | None = None,
    text: str | None = None,
    image: bytes | None = None,
    audio: bytes | None = None,
    audio_mime: str = "audio/wav",
    lang: str = "zh",
    with_avatar: bool = True,
    with_perception: bool = True,
) -> DialogState:
    """执行一次完整的数字人对话（含感知与驱动）。"""
    initial: DialogState = {
        "session_id": session_id or "",
        "lang": lang,
        "text": text or "",
        "image": image,
        "audio": audio,
        "audio_mime": audio_mime,
        "with_avatar": with_avatar,
        "with_perception": with_perception,
    }
    return get_dialog_graph().invoke(initial)


__all__ = ["DialogService", "GESTURE_ACTIONS", "run_dialog"]


class DialogService:
    """对外门面：保持与其它服务一致的调用方式。"""

    def handle(self, **kwargs: Any) -> dict[str, Any]:
        state = run_dialog(**kwargs)
        hits = state.get("hits") or []
        return {
            "session_id": state.get("session_id"),
            "intent": state.get("intent"),
            "question": state.get("question"),
            "answer_text": state.get("answer") or "",
            "citations": [
                {
                    "kb_id": hit.chunk.id,
                    "title": hit.chunk.title,
                    "source": hit.chunk.source,
                    "score": round(float(hit.score), 4),
                    "rerank_score": round(float(hit.rerank_score), 4) if hit.rerank_score is not None else None,
                }
                for hit in hits[:3]
            ],
            "medias": [
                {"type": hit.chunk.modality, "url": hit.chunk.media_uri} for hit in hits if hit.chunk.media_uri
            ],
            "ocr_text": state.get("ocr_text") or None,
            "asr_text": state.get("asr_text") or None,
            # 前端据此提示"这次没听到语音"，否则游客会以为自己的语音被忽略了
            "asr_degraded": state.get("asr_degraded") or None,
            "perception": state.get("perception"),
            "avatar": state.get("avatar"),
            "session_turns": state.get("session_turns", 0),
            "lang": state.get("lang", "zh"),
            "workflow": "langgraph:normalize→route→retrieve→generate→respond",
        }
