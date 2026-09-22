"""工单18 · 数字人接口

工单编号：人工智能CV-AIGC-18-文旅Agent任务工单-智能导览与互动体验
  GET  /api/v1/avatar         数字人形象信息（2D/3D、引擎、音色、情绪与动作集）
  POST /api/v1/avatar/drive   文本 → 语音 + 唇形视位 + 表情/动作参数
  POST /api/v1/avatar/greet   感知触发的主动问候（挥手 / 点赞 / 指向 / 比心）
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter

from ...schemas import ApiResponse, AvatarDriveRequest, AvatarGreetRequest
from ...services.avatar import AvatarService

router = APIRouter(prefix="/avatar", tags=["avatar"])


@router.get("", response_model=ApiResponse)
def profile() -> ApiResponse:
    return ApiResponse(data=AvatarService().profile(), trace_id=uuid.uuid4().hex)


@router.post("/drive", response_model=ApiResponse)
def drive(payload: AvatarDriveRequest) -> ApiResponse:
    data = AvatarService().drive(payload.text, lang=payload.lang, emotion=payload.emotion, motion=payload.motion)
    return ApiResponse(data=data, trace_id=uuid.uuid4().hex)


@router.post("/greet", response_model=ApiResponse)
def greet(payload: AvatarGreetRequest) -> ApiResponse:
    return ApiResponse(data=AvatarService().greet(gesture=payload.gesture, lang=payload.lang), trace_id=uuid.uuid4().hex)
