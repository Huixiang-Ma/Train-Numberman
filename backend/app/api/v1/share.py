"""工单19 · 内容分享接口

工单编号：人工智能CV-AIGC-19-文旅Agent任务工单-创意策划与内容生成
对应 docs/05 第五章接口表：POST /api/v1/share（生成分享链接/海报）
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException, Response

from ...schemas import ApiResponse, ShareRequest
from ...services.creative_common import ContentRejected
from ...services.share import ShareService

logger = logging.getLogger("wenlv.api.share")

router = APIRouter(prefix="/share", tags=["share"])


@router.post("", response_model=ApiResponse)
def create_share(payload: ShareRequest) -> ApiResponse:
    """为生成内容创建分享链接与海报。

    链接用随机 token 而非自增 id：分享内容多为游客个人照片，不能可枚举。
    """
    try:
        data = ShareService().create(payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, ContentRejected) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("分享创建失败：%s", exc)
        raise HTTPException(status_code=500, detail=f"分享创建失败：{exc}") from exc
    return ApiResponse(data=data, trace_id=uuid.uuid4().hex)


@router.get("/{token}", response_model=ApiResponse)
def resolve_share(token: str) -> ApiResponse:
    """按 token 读取分享内容（分享落地页使用，公开）。"""
    try:
        data = ShareService().resolve(token)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ApiResponse(data=data, trace_id=uuid.uuid4().hex)


@router.get("/{token}/poster")
def share_poster(token: str) -> Response:
    """分享海报图片（视频类自动取首帧作为封面）。"""
    try:
        data = ShareService().poster_bytes(token)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )
