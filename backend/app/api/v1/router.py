"""工单17 · v1 路由汇总

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成
"""
from __future__ import annotations

from fastapi import APIRouter

from . import (
    activity,
    analytics,
    audit,
    auth,
    avatar,
    creation,
    dialog,
    health,
    itinerary,
    kb,
    media,
    park,
    perception,
    query,
    search,
    service,
    session,
    share,
    ticket,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(kb.router)
api_router.include_router(search.router)
api_router.include_router(query.router)
api_router.include_router(media.router)

# 阶段三（工单18）：会话 / 数字人对话 / 数字人驱动 / 实时感知
api_router.include_router(session.router)
api_router.include_router(dialog.router)
api_router.include_router(avatar.router)
api_router.include_router(perception.router)

# 阶段四（工单19）：线路策划 / 活动推荐 / 内容生成 / 分享
api_router.include_router(itinerary.router)
api_router.include_router(activity.router)
api_router.include_router(creation.router)
api_router.include_router(share.router)

# 阶段五（工单20）：审计日志与合规自查
api_router.include_router(audit.router)

# docs/09 通用化（G1）：目的地 / 景区三层归属
api_router.include_router(park.router)

# docs/09 通用化（G3）：票种 / 时段库存 / 订单 / 电子票 / 核销
api_router.include_router(ticket.router)

# docs/09 通用化（G4）：游客服务工单与评价
api_router.include_router(service.router)
api_router.include_router(service.review_router)

# docs/09 通用化（G5）：经营分析与游客需求洞察
api_router.include_router(analytics.router)
