"""工单19 · 活动与体验创意推荐接口

工单编号：人工智能CV-AIGC-19-文旅Agent任务工单-创意策划与内容生成
对应 docs/05 第五章接口表：POST /api/v1/activity/recommend
（攻略与流程图见 /api/v1/create/guide）
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException

from ...schemas import ActivityRecommendRequest, ApiResponse
from ...services.activity import ActivityService
from ...services.creative_common import ContentRejected

logger = logging.getLogger("wenlv.api.activity")

router = APIRouter(prefix="/activity", tags=["activity"])


@router.post("/recommend", response_model=ApiResponse)
def recommend(payload: ActivityRecommendRequest) -> ApiResponse:
    """结合游客当前位置与兴趣推荐可参与的活动。

    带经纬度时用 PostGIS 在库内按球面距离排序并按半径过滤；
    未带定位（游客未授权）则退化为按兴趣匹配排序，不阻断推荐。
    """
    try:
        data = ActivityService().recommend(payload)
    except ContentRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("活动推荐失败：%s", exc)
        raise HTTPException(status_code=500, detail=f"活动推荐失败：{exc}") from exc
    return ApiResponse(data=data, trace_id=uuid.uuid4().hex)
