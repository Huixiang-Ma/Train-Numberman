"""docs/09 G5 · 数据分析与需求洞察接口（批次 6）

工单编号：人工智能CV-AIGC-16-【必选】文旅Agent任务工单-需求分析与功能设计

权限：经营数据与游客提问记录属运营敏感信息，统一 require_editor
（与 audit 的处理一致，理由相同：能被用来推断经营状况与游客行为）。
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from ...schemas import ApiResponse
from ...services.analytics import AnalyticsService
from ..deps import require_editor

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/business", response_model=ApiResponse)
def business(
    park_id: str | None = None,
    days: int = Query(30, ge=1, le=180),
    _=Depends(require_editor),
) -> ApiResponse:
    """经营总览：票务、票种结构、核销时段分布、满意度、服务分布、内容产量。

    返回值里的 `gaps` 列出**没有数据源的指标及原因**，页面必须如实展示 ——
    空着的模块比编出来的折线图更诚实。
    """
    return ApiResponse(data=AnalyticsService().business_overview(park_id=park_id, days=days), trace_id=uuid.uuid4().hex)


@router.get("/parks", response_model=ApiResponse)
def parks(days: int = Query(30, ge=1, le=180), _=Depends(require_editor)) -> ApiResponse:
    """跨景区对比。这是"通用多景区"相对"单景区"的直接增量价值。"""
    items = AnalyticsService().park_comparison(days=days)
    return ApiResponse(data={"items": items, "total": len(items)}, trace_id=uuid.uuid4().hex)


@router.get("/insight", response_model=ApiResponse)
def insight(days: int = Query(30, ge=1, le=180), _=Depends(require_editor)) -> ApiResponse:
    """游客需求洞察（工单16 §2.1 第 4 条）。"""
    return ApiResponse(data=AnalyticsService().insight(days=days), trace_id=uuid.uuid4().hex)


@router.get("/datasets", response_model=ApiResponse)
def datasets(_=Depends(require_editor)) -> ApiResponse:
    """可供查询的结构化数据集清单（数据查询页的选项来源）。"""
    items = AnalyticsService().datasets()
    return ApiResponse(data={"items": items, "total": len(items)}, trace_id=uuid.uuid4().hex)


@router.get("/dataset/{name}", response_model=ApiResponse)
def dataset(name: str, limit: int = Query(200, ge=1, le=1000), _=Depends(require_editor)) -> ApiResponse:
    data = AnalyticsService().dataset(name, limit=limit)
    if data is None:
        raise HTTPException(status_code=404, detail="数据集不存在")
    return ApiResponse(data=data, trace_id=uuid.uuid4().hex)
