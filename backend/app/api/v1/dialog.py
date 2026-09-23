"""工单18 · 数字人对话接口（Agent 调度入口）

工单编号：人工智能CV-AIGC-18-文旅Agent任务工单-智能导览与互动体验
  POST /api/v1/dialog              文本对话（多轮 + 数字人驱动）
  POST /api/v1/dialog/multimodal   多模态对话（文本 + 图片 + 语音）
"""
from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ...schemas import ApiResponse, DialogRequest
from ...services.analytics import record_query
from ...services.dialog import DialogService
from ...services.retrieval import RetrievalService

router = APIRouter(tags=["dialog"])


def _record(data: dict, *, source: str, question: str, has_image: bool, has_audio: bool, started: float) -> None:
    """把一次对话落进提问埋点。

    意图与引文数都取自**后端自己的判定结果**，不在前端猜；
    `intent` 是 DialogService 的输出，正是「需求洞察」里意图分布的来源。
    """
    record_query(
        source=source,
        question=question or "",
        intent=str(data.get("intent") or ""),
        session_id=str(data.get("session_id") or ""),
        lang=str(data.get("lang") or "zh"),
        citations=len(data.get("citations") or []),
        has_image=has_image,
        has_audio=has_audio or bool(data.get("asr_text")),
        latency_ms=int((time.perf_counter() - started) * 1000),
    )


@router.post("/dialog", response_model=ApiResponse)
def dialog(payload: DialogRequest) -> ApiResponse:
    started = time.perf_counter()
    data = DialogService().handle(
        session_id=payload.session_id,
        text=payload.text,
        lang=payload.lang,
        with_avatar=payload.with_avatar,
        with_perception=payload.with_perception,
    )
    _record(data, source="dialog", question=payload.text or "", has_image=False, has_audio=False, started=started)
    return ApiResponse(data=data, trace_id=uuid.uuid4().hex)


@router.post("/dialog/multimodal", response_model=ApiResponse)
async def dialog_multimodal(
    session_id: str | None = Form(None),
    text: str | None = Form(None),
    lang: str = Form("zh"),
    with_avatar: bool = Form(True),
    with_perception: bool = Form(True),
    image: UploadFile | None = File(None),
    audio: UploadFile | None = File(None),
) -> ApiResponse:
    image_bytes = await image.read() if image is not None else None
    if image_bytes:
        try:
            RetrievalService.validate_image(image_bytes)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    started = time.perf_counter()
    data = DialogService().handle(
        session_id=session_id,
        text=text,
        image=image_bytes,
        audio=(await audio.read()) if audio is not None else None,
        audio_mime=(audio.content_type if audio else "audio/wav") or "audio/wav",
        lang=lang,
        with_avatar=with_avatar,
        with_perception=with_perception,
    )
    _record(
        data,
        source="dialog",
        question=text or "",
        has_image=image_bytes is not None,
        has_audio=audio is not None,
        started=started,
    )
    return ApiResponse(data=data, trace_id=uuid.uuid4().hex)
