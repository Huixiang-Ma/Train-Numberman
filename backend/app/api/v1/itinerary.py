"""工单19 · 个性化旅游线路与活动创意生成接口

工单编号：人工智能CV-AIGC-19-文旅Agent任务工单-创意策划与内容生成
对应 docs/05 第五章接口表：POST /api/v1/itinerary/plan
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException

from ...schemas import ApiResponse, ItineraryPlanRequest
from ...services.creative_common import ContentRejected
from ...services.itinerary import ItineraryService

logger = logging.getLogger("wenlv.api.itinerary")

router = APIRouter(prefix="/itinerary", tags=["itinerary"])


@router.post("/plan", response_model=ApiResponse)
def plan_itinerary(payload: ItineraryPlanRequest) -> ApiResponse:
    """按兴趣 / 主题 / 时长生成专属行程（公开接口，无需令牌）。

    行程分站取自真实景点与活动数据；模型不可用时自动降级为确定性排程，
    因此该接口在检索或生成链路异常时依然可用。
    """
    try:
        data = ItineraryService().plan(payload)
    except ContentRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # 兜底：把内部异常转成可读的 500，避免前端只看到网络错误
        logger.exception("行程策划失败：%s", exc)
        raise HTTPException(status_code=500, detail=f"行程策划失败：{exc}") from exc
    return ApiResponse(data=data, trace_id=uuid.uuid4().hex)
