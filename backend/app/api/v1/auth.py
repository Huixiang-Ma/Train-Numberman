"""工单17 · 授权接口（OAuth2 密码模式 + JWT）

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from ...core.config import get_settings
from ...core.security import authenticate, create_access_token
from ...schemas import ApiResponse, TokenOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token", response_model=ApiResponse)
def issue_token(form: OAuth2PasswordRequestForm = Depends()) -> ApiResponse:
    role = authenticate(form.username, form.password)
    if role is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    settings = get_settings()
    token = create_access_token(subject=form.username, role=role)
    data = TokenOut(
        access_token=token,
        expires_in=settings.access_token_expire_minutes * 60,
        role=role,
    )
    return ApiResponse(data=data.model_dump(), trace_id=uuid.uuid4().hex)
