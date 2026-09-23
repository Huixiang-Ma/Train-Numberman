"""工单18 · 实时感知接口

工单编号：人工智能CV-AIGC-18-文旅Agent任务工单-智能导览与互动体验
  POST /api/v1/perception/analyze   单帧分析（检测跟踪 / 分类 / 分割 / 手势 / 表情 / OCR）
  WS   /api/v1/ws/perception        实时感知流（逐帧回传，低延迟）
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict
from typing import Any, Sequence

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from ...core.config import get_settings
from ...schemas import ApiResponse
from ...services.avatar import AvatarService
from ...services.avatar_interaction import AvatarInteractionCoordinator, CLARIFICATION_TEXT
from ...services.generation import GenerationService
from ...services.perception import PerceptionService
from ...services.retrieval import RetrievalService

router = APIRouter(tags=["perception"])
logger = logging.getLogger(__name__)


@router.post("/perception/analyze", response_model=ApiResponse)
async def analyze(
    frame: UploadFile = File(...),
    with_classify: bool = Form(False),
    with_segments: bool = Form(False),
    with_ocr: bool = Form(False),
) -> ApiResponse:
    raw = await frame.read()
    try:
        RetrievalService.validate_image(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    service = PerceptionService()
    result = service.analyze(
        raw, with_detection=True, with_classify=with_classify, with_segments=with_segments, with_ocr=with_ocr
    )
    payload = service.to_payload(result)
    payload["providers"] = service.providers
    payload["suggestion"] = service.suggest(result)
    payload["ocr_text"] = service.read_text(raw) if with_ocr else ""
    return ApiResponse(data=payload, trace_id=uuid.uuid4().hex)


_MAX_INTERACTION_TEXT_LENGTH = 200
_MAX_SOURCE_FIELD_LENGTH = 40


def _bounded_source_field(value: Any, fallback: str) -> str:
    field = str(value or "").strip() or fallback
    if len(field) <= _MAX_SOURCE_FIELD_LENGTH:
        return field
    return f"{field[: _MAX_SOURCE_FIELD_LENGTH - 1]}…"


def _source_suffix(hits: Sequence[Any]) -> str:
    """Build a bounded source line with one identifiable title and origin."""
    hit = next(iter(hits), None)
    chunk = getattr(hit, "chunk", None)
    title = _bounded_source_field(getattr(chunk, "title", ""), "景区资料")
    source = _bounded_source_field(getattr(chunk, "source", ""), "景区知识库")
    return f"资料来源：{title}（{source}）。"


def _with_sources(text: str, hits: Sequence[Any]) -> str:
    source_suffix = _source_suffix(hits)
    answer = (text or "").strip()
    if "资料来源：" in answer:
        answer = answer.split("资料来源：", 1)[0].rstrip(" ，；;\n\t")
    answer_budget = max(0, _MAX_INTERACTION_TEXT_LENGTH - len(source_suffix))
    return f"{answer[:answer_budget]}{source_suffix}"


async def _close_safely(websocket: WebSocket, code: int = 1011) -> None:
    try:
        await websocket.close(code=code)
    except Exception:
        pass


@router.websocket("/ws/perception")
async def perception_stream(websocket: WebSocket) -> None:
    """实时感知流。

    客户端 → 服务端
      · 二进制帧：JPEG 图像
      · 文本帧：JSON 配置，如 {"withSegments": true} / {"ping": true}
    服务端 → 客户端
      · {"type":"ready","providers":{...}}
      · {"type":"perception","data":{...},"suggestion":{...},"interaction":{...}}
      · {"type":"pong"}

    感知、检索、生成和数字人驱动均为同步服务，放到线程池执行，避免阻塞
    WebSocket 事件循环；协调器和服务实例都属于当前连接，断开后不会复用。
    """
    await websocket.accept()
    try:
        settings = get_settings()
        service = await run_in_threadpool(PerceptionService)
        coordinator = AvatarInteractionCoordinator(
            stable_frames=settings.avatar_stable_frames,
            cooldown_seconds=settings.avatar_auto_explain_cooldown_seconds,
        )
    except Exception as exc:
        logger.warning("WebSocket 感知服务初始化失败：%s: %s", type(exc).__name__, exc)
        await websocket.send_text(
            json.dumps(
                {"type": "error", "code": "perception_unavailable", "message": "实时感知暂不可用，请稍后重试。"},
                ensure_ascii=False,
            )
        )
        await _close_safely(websocket)
        return

    avatar: AvatarService | None
    avatar_degraded: dict[str, str] | None = None
    try:
        avatar = await run_in_threadpool(AvatarService)
    except Exception as exc:
        logger.warning("Avatar 服务初始化失败，感知流继续运行：%s: %s", type(exc).__name__, exc)
        avatar = None
        avatar_degraded = {"component": "avatar", "message": "数字人驱动暂不可用，感知流仍可继续。"}

    retrieval: RetrievalService | None = None
    generation: GenerationService | None = None
    options = {"withClassify": False, "withSegments": False, "withOcr": False}

    try:
        ready: dict[str, Any] = {
            "type": "ready",
            "providers": service.providers,
            "message": "实时感知已就绪（工单18）",
        }
        if avatar_degraded is not None:
            ready["degraded"] = avatar_degraded
        await websocket.send_text(json.dumps(ready, ensure_ascii=False))
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break

            frame = message.get("bytes")
            text = message.get("text")

            if text:
                try:
                    config = json.loads(text)
                except json.JSONDecodeError:
                    config = {}
                if config.get("ping"):
                    await websocket.send_text(json.dumps({"type": "pong"}, ensure_ascii=False))
                    continue
                for key in ("withClassify", "withSegments", "withOcr"):
                    if key in config:
                        options[key] = bool(config[key])
                if frame is None:
                    continue

            if not frame:
                continue

            try:
                result = await run_in_threadpool(
                    service.analyze,
                    frame,
                    with_detection=True,
                    with_classify=options["withClassify"],
                    with_segments=options["withSegments"],
                    with_ocr=options["withOcr"],
                )
                payload = service.to_payload(result)
                suggestion = service.suggest(result)
                event = coordinator.observe(result)
            except Exception as exc:
                logger.warning("WebSocket 单帧感知失败：%s: %s", type(exc).__name__, exc)
                fallback = {
                    "type": "perception",
                    "data": {},
                    "suggestion": None,
                    "interaction": {
                        "kind": "clarification",
                        "text": CLARIFICATION_TEXT,
                        "target": None,
                        "confidence": 0.0,
                        "motion": "nod",
                        "emotion": "gentle",
                        "gesture": None,
                        "drive": None,
                    },
                    "degraded": {"component": "perception", "message": "当前画面分析失败，请重新拍摄。"},
                }
                await websocket.send_text(json.dumps(fallback, ensure_ascii=False))
                continue
            response: dict = {
                "type": "perception",
                "data": payload,
                "suggestion": suggestion,
                "interaction": None,
            }

            if event is not None:
                interaction_text = event.text
                interaction_kind = event.kind
                interaction_emotion = event.emotion
                interaction_motion = event.motion
                event_drive = None
                hits: list[Any] = []
                avatar_payload: dict[str, Any] | None = None
                if event.kind == "explanation" and event.target:
                    query = event.target
                    try:
                        if retrieval is None:
                            retrieval = await run_in_threadpool(RetrievalService)
                        hits = await run_in_threadpool(
                            retrieval.text_to_text,
                            query,
                            settings.avatar_auto_explain_top_k,
                        )
                    except Exception as exc:
                        logger.warning("自动讲解检索失败：%s: %s", type(exc).__name__, exc)
                        hits = []

                    if hits:
                        try:
                            if generation is None:
                                generation = await run_in_threadpool(GenerationService)
                            generated, degraded = await run_in_threadpool(
                                generation.generate_with_status,
                                query,
                                hits,
                            )
                            if degraded:
                                interaction_kind = "clarification"
                            elif not isinstance(generated, str) or not generated.strip():
                                raise ValueError("生成结果为空")
                            else:
                                interaction_text = _with_sources(generated.strip(), hits)
                        except Exception as exc:
                            logger.warning("自动讲解生成失败：%s: %s", type(exc).__name__, exc)
                            interaction_kind = "clarification"
                    else:
                        interaction_kind = "clarification"

                    if interaction_kind == "clarification":
                        interaction_text = CLARIFICATION_TEXT
                        interaction_emotion = "gentle"
                        interaction_motion = "nod"

                try:
                    if avatar is None:
                        raise RuntimeError("Avatar 服务不可用")
                    if event.kind == "greeting":
                        avatar_payload = await run_in_threadpool(avatar.greet, gesture=event.gesture)
                        interaction_text = str(avatar_payload.get("text") or interaction_text)
                        event_drive = avatar_payload.get("drive") or {}
                    else:
                        event_drive = await run_in_threadpool(
                            avatar.drive,
                            interaction_text,
                            emotion=interaction_emotion,
                            motion=interaction_motion,
                        )
                        avatar_payload = {
                            "text": interaction_text,
                            "gesture": event.gesture or event.target or "",
                            "drive": event_drive,
                        }
                except Exception as exc:
                    logger.warning("Avatar 交互驱动失败：%s: %s", type(exc).__name__, exc)
                    interaction_kind = "clarification"
                    interaction_text = CLARIFICATION_TEXT
                    interaction_emotion = "gentle"
                    interaction_motion = "nod"
                    event_drive = None
                    avatar_payload = None
                    response["degraded"] = {
                        "component": "avatar",
                        "message": "数字人驱动暂不可用，请参考文字提示。",
                    }

                interaction = asdict(event)
                interaction.update(
                    kind=interaction_kind,
                    text=interaction_text,
                    emotion=interaction_emotion,
                    motion=interaction_motion,
                    drive=event_drive,
                )
                response["interaction"] = interaction
                if avatar_payload is not None:
                    response["avatar"] = avatar_payload

            await websocket.send_text(json.dumps(response, ensure_ascii=False))
    except WebSocketDisconnect:
        return
    except Exception as exc:
        logger.warning("WebSocket 感知连接异常，安全关闭：%s: %s", type(exc).__name__, exc)
        await _close_safely(websocket)
