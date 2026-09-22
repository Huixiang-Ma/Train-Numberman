"""工单17 · 媒体接口（对象存储 / 语音合成 / 多语言字幕）

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, UploadFile

from ...providers.registry import get_storage, get_tts
from ...schemas import ApiResponse, SubtitleRequest, TTSRequest
from ...services.generation import GenerationService
from ...services.retrieval import RetrievalService
from ..deps import require_editor

router = APIRouter(prefix="/media", tags=["media"])


@router.post("/upload", response_model=ApiResponse)
async def upload(file: UploadFile = File(...), _=Depends(require_editor)) -> ApiResponse:
    raw = await file.read()
    media_type = RetrievalService.guess_media_type(file.filename or "")
    key = f"{media_type}/{uuid.uuid4().hex}-{file.filename}"
    uri = get_storage().put_object(key, raw, content_type=file.content_type or "application/octet-stream")
    return ApiResponse(
        data={"uri": uri, "key": key, "media_type": media_type, "size_bytes": len(raw)},
        trace_id=uuid.uuid4().hex,
    )


@router.post("/tts", response_model=ApiResponse)
def tts(payload: TTSRequest) -> ApiResponse:
    return ApiResponse(
        data=get_tts().synthesize(payload.text, lang=payload.lang, voice=payload.voice),
        trace_id=uuid.uuid4().hex,
    )


@router.post("/subtitle", response_model=ApiResponse)
def subtitle(payload: SubtitleRequest) -> ApiResponse:
    generation = GenerationService()
    tracks = {payload.lang: payload.text}
    for target in payload.target_langs:
        if target == payload.lang:
            continue
        tracks[target] = generation.translate(payload.text, target)
    return ApiResponse(data={"tracks": tracks}, trace_id=uuid.uuid4().hex)
