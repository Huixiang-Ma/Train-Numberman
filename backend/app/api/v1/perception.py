"""工单18 · 实时感知接口

工单编号：人工智能CV-AIGC-18-文旅Agent任务工单-智能导览与互动体验
  POST /api/v1/perception/analyze   单帧分析（检测跟踪 / 分类 / 分割 / 手势 / 表情 / OCR）
  WS   /api/v1/ws/perception        实时感知流（逐帧回传，低延迟）
"""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect

from ...schemas import ApiResponse
from ...services.avatar import AvatarService
from ...services.perception import PerceptionService
from ...services.retrieval import RetrievalService

router = APIRouter(tags=["perception"])


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


@router.websocket("/ws/perception")
async def perception_stream(websocket: WebSocket) -> None:
    """实时感知流。

    客户端 → 服务端
      · 二进制帧：JPEG 图像
      · 文本帧：JSON 配置，如 {"withSegments": true} / {"ping": true}
    服务端 → 客户端
      · {"type":"ready","providers":{...}}
      · {"type":"perception","data":{...},"suggestion":{...},"avatar":{...}}
      · {"type":"pong"}
    """
    await websocket.accept()
    service = PerceptionService()
    avatar = AvatarService()
    options = {"withClassify": False, "withSegments": False, "withOcr": False}

    await websocket.send_text(
        json.dumps(
            {"type": "ready", "providers": service.providers, "message": "实时感知已就绪（工单18）"},
            ensure_ascii=False,
        )
    )

    try:
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

            result = service.analyze(
                frame,
                with_detection=True,
                with_classify=options["withClassify"],
                with_segments=options["withSegments"],
                with_ocr=options["withOcr"],
            )
            payload = service.to_payload(result)
            suggestion = service.suggest(result)

            response: dict = {"type": "perception", "data": payload, "suggestion": suggestion}
            if suggestion and suggestion.get("action") == "greet":
                response["avatar"] = avatar.greet(gesture=suggestion.get("gesture"))
            await websocket.send_text(json.dumps(response, ensure_ascii=False))
    except WebSocketDisconnect:
        return
