"""docs/09 G4 · 游客服务与评价接口（批次 5）

工单编号：人工智能CV-AIGC-19-文旅Agent任务工单-创意策划与内容生成

两个 router（service / review）放在同一文件：它们共用同一个服务对象，
拆两个文件会让"工单与评价互相关联"这一条设计意图在目录结构上被割裂。

权限：游客侧（提交工单、提交评价、看自己的工单、看景区评价）公开；
处理侧（受理回复、改状态、汇总）挂 require_editor，对应「客服/游客服务人员」。
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from ...schemas import (
    ApiResponse,
    ReviewIn,
    ReviewReplyIn,
    ServiceReplyIn,
    ServiceRequestIn,
    ServiceStatusIn,
)
from ...services.service_request import ReviewService, ServiceRequestService
from ..deps import require_editor

router = APIRouter(prefix="/service", tags=["service"])
review_router = APIRouter(prefix="/review", tags=["review"])


# ============================================================ 游客服务（游客侧）

@router.post("/request", response_model=ApiResponse)
def create_request(payload: ServiceRequestIn) -> ApiResponse:
    """提交服务工单：咨询 / 投诉建议 / 失物招领 / 紧急求助。"""
    data, error = ServiceRequestService().create(
        park_id=payload.park_id,
        visitor_ref=payload.visitor_ref,
        category=payload.category,
        content=payload.content,
        contact=payload.contact,
        urgent=payload.urgent,
    )
    if error:
        raise HTTPException(status_code=400, detail=error)
    return ApiResponse(data=data, trace_id=uuid.uuid4().hex)


@router.get("/my", response_model=ApiResponse)
def my_requests(visitor_ref: str = "", limit: int = Query(50, ge=1, le=200)) -> ApiResponse:
    """我提交过的工单，供游客端跟进处理进度。"""
    items = ServiceRequestService().list(limit=limit)
    if visitor_ref:
        items = [item for item in items if item["visitor_ref"] == visitor_ref]
    return ApiResponse(data={"items": items, "total": len(items)}, trace_id=uuid.uuid4().hex)


# ============================================================ 游客服务（处理侧）

@router.get("/admin/requests", response_model=ApiResponse)
def admin_requests(
    park_id: str | None = None,
    status: str | None = None,
    category: str | None = None,
    limit: int = Query(100, ge=1, le=300),
    _=Depends(require_editor),
) -> ApiResponse:
    items = ServiceRequestService().list(park_id=park_id, status=status, category=category, limit=limit)
    return ApiResponse(data={"items": items, "total": len(items)}, trace_id=uuid.uuid4().hex)


@router.get("/admin/stats", response_model=ApiResponse)
def service_stats(park_id: str | None = None, _=Depends(require_editor)) -> ApiResponse:
    return ApiResponse(data=ServiceRequestService().stats(park_id=park_id), trace_id=uuid.uuid4().hex)


@router.post("/admin/requests/{request_id}/reply", response_model=ApiResponse)
def reply_request(request_id: str, payload: ServiceReplyIn, _=Depends(require_editor)) -> ApiResponse:
    if not payload.reply.strip():
        raise HTTPException(status_code=400, detail="回复内容不能为空")
    data = ServiceRequestService().reply(request_id, payload.reply, handled_by=payload.handled_by)
    if data is None:
        raise HTTPException(status_code=404, detail="工单不存在")
    return ApiResponse(data=data, trace_id=uuid.uuid4().hex)


@router.put("/admin/requests/{request_id}/status", response_model=ApiResponse)
def set_request_status(request_id: str, payload: ServiceStatusIn, _=Depends(require_editor)) -> ApiResponse:
    data, error = ServiceRequestService().set_status(request_id, payload.status)
    if error:
        raise HTTPException(status_code=400, detail=error)
    if data is None:
        raise HTTPException(status_code=404, detail="工单不存在")
    return ApiResponse(data=data, trace_id=uuid.uuid4().hex)


# ================================================================ 评价（游客侧）

@review_router.post("", response_model=ApiResponse)
def create_review(payload: ReviewIn) -> ApiResponse:
    """提交评价。同一订单重复提交会**覆盖**上一次，避免一趟行程刷出多份评价。"""
    data, error = ReviewService().create(
        park_id=payload.park_id,
        order_id=payload.order_id,
        visitor_ref=payload.visitor_ref,
        rating=payload.rating,
        content=payload.content,
        tags=payload.tags,
    )
    if error:
        raise HTTPException(status_code=400, detail=error)
    return ApiResponse(data=data, trace_id=uuid.uuid4().hex)


@review_router.get("/park/{park_id}", response_model=ApiResponse)
def park_reviews(park_id: str, limit: int = Query(50, ge=1, le=200)) -> ApiResponse:
    """景区评价列表（游客端详情页与管理端共用）。"""
    service = ReviewService()
    items = service.list(park_id=park_id, limit=limit)
    return ApiResponse(
        data={"items": items, "total": len(items), "summary": service.summary(park_id=park_id)},
        trace_id=uuid.uuid4().hex,
    )


@review_router.get("/summary", response_model=ApiResponse)
def review_summary(park_id: str | None = None, _=Depends(require_editor)) -> ApiResponse:
    """评分汇总：均分 + 分布。"""
    return ApiResponse(data=ReviewService().summary(park_id=park_id), trace_id=uuid.uuid4().hex)


@review_router.get("/admin/list", response_model=ApiResponse)
def admin_reviews(
    park_id: str | None = None,
    limit: int = Query(100, ge=1, le=300),
    _=Depends(require_editor),
) -> ApiResponse:
    items = ReviewService().list(park_id=park_id, limit=limit)
    return ApiResponse(data={"items": items, "total": len(items)}, trace_id=uuid.uuid4().hex)


@review_router.post("/admin/{review_id}/reply", response_model=ApiResponse)
def reply_review(review_id: str, payload: ReviewReplyIn, _=Depends(require_editor)) -> ApiResponse:
    """景区回复评价。"""
    if not payload.reply.strip():
        raise HTTPException(status_code=400, detail="回复内容不能为空")
    data = ReviewService().reply(review_id, payload.reply)
    if data is None:
        raise HTTPException(status_code=404, detail="评价不存在")
    return ApiResponse(data=data, trace_id=uuid.uuid4().hex)
