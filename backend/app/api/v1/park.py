"""工单17 · 目的地 / 景区只读接口（docs/09 G1：通用化三层归属）

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成

为什么是公开接口：游客端的「发现」与「景区详情」在未登录时也必须能看，
与 health.py 的处理一致（不挂 RBAC 依赖）。写入接口属管理端，
在批次 4/5 提供并另加 require_editor。

沿用 health.py 的写法：不带 prefix，路径显式写全（/destination、/park）。
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query

from ...schemas import ApiResponse
from ...services.park import ParkService

router = APIRouter(tags=["park"])


@router.get("/destination", response_model=ApiResponse)
def list_destinations() -> ApiResponse:
    items = ParkService().destinations()
    return ApiResponse(data={"items": items, "total": len(items)}, trace_id=uuid.uuid4().hex)


@router.get("/park", response_model=ApiResponse)
def list_parks(
    destination_id: str | None = None,
    keyword: str | None = None,
    tag: str | None = None,
    near_lat: float | None = None,
    near_lon: float | None = None,
    limit: int = Query(50, ge=1, le=200),
) -> ApiResponse:
    items = ParkService().parks(
        destination_id=destination_id,
        keyword=keyword,
        tag=tag,
        near_lat=near_lat,
        near_lon=near_lon,
        limit=limit,
    )
    return ApiResponse(
        data={
            "items": items,
            "total": len(items),
            # 前端据此决定要不要显示"按距离排序"的提示
            "has_geo": near_lat is not None and near_lon is not None,
        },
        trace_id=uuid.uuid4().hex,
    )


@router.get("/park/{park_id}", response_model=ApiResponse)
def get_park(park_id: str) -> ApiResponse:
    item = ParkService().park(park_id)
    if item is None:
        raise HTTPException(status_code=404, detail="景区不存在")
    return ApiResponse(data=item, trace_id=uuid.uuid4().hex)
