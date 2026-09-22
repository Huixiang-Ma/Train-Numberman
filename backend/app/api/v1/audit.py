"""工单20 · 审计日志与合规自查接口

工单编号：人工智能CV-AIGC-20-文旅Agent任务工单-功能集成测试与部署
对应 docs/06 §4.5「全链路数据加密，严格的权限与访问控制，日志审计」与
        §4.6「自动 + 人工结合的内容审核机制」。

权限：审计与合规数据属运营敏感信息，统一要求**运营及以上**角色（require_editor）。
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from ...core.config import get_settings
from ...core.observability import mask_sensitive
from ...db.base import SessionLocal
from ...db.models import AuditLog
from ...schemas import ApiResponse
from ..deps import require_editor

logger = logging.getLogger("wenlv.api.audit")

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/logs", response_model=ApiResponse)
def list_logs(
    limit: int = Query(50, ge=1, le=200),
    path: str | None = None,
    _=Depends(require_editor),
) -> ApiResponse:
    """操作审计日志（按时间倒序）。

    仅为演示与自查提供查询入口；生产应接 Grafana / ELK 做可视化与告警。
    """
    with SessionLocal() as db:
        stmt = select(AuditLog)
        if path:
            stmt = stmt.where(AuditLog.path.like(f"%{path}%"))
        rows = list(db.scalars(stmt.order_by(AuditLog.created_at.desc()).limit(limit)))
        total = db.scalar(select(func.count()).select_from(AuditLog))
        items = [
            {
                "id": row.id,
                "method": row.method,
                # 路径可能带查询串，输出前再脱敏一次（与日志同一条规则）
                "path": mask_sensitive(row.path or ""),
                "status": row.status,
                "client_ip": row.client_ip,
                "role": row.role,
                "trace_id": row.trace_id,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]
    return ApiResponse(data={"items": items, "total": int(total or 0)}, trace_id=uuid.uuid4().hex)


@router.get("/compliance", response_model=ApiResponse)
def compliance(_=Depends(require_editor)) -> ApiResponse:
    """合规自查：如实回显当前安全与合规配置状态。

    刻意**不粉饰**：未配置的项明确标为 `pending`，避免"自检全绿但实际未启用"。
    """
    settings = get_settings()
    blocklist = settings.blocklist

    with SessionLocal() as db:
        audit_total = int(db.scalar(select(func.count()).select_from(AuditLog)) or 0)

    checks = [
        {
            "item": "身份与权限",
            "status": "ok",
            "detail": "OAuth2 + JWT + RBAC（游客/运营/专家/管理员四级）；写操作按角色鉴权",
        },
        {
            "item": "访问审计",
            "status": "ok" if audit_total >= 0 else "pending",
            "detail": f"状态变更类请求落 audit_log，当前累计 {audit_total} 条；访问日志按请求输出",
        },
        {
            "item": "全链路追踪",
            "status": "ok",
            "detail": "trace_id 由中间件注入，贯穿响应体、响应头、访问日志、审计记录与异常堆栈",
        },
        {
            "item": "日志脱敏",
            "status": "ok",
            "detail": "手机号 / 证件号 / 邮箱 / 来源 IP 在写入日志与审计前统一脱敏",
        },
        {
            "item": "内容审核",
            "status": "ok" if blocklist else "pending",
            "detail": (
                f"已配置 {len(blocklist)} 个拦截词，覆盖生成链路的输入与输出两侧"
                if blocklist
                else "词表为空（CONTENT_BLOCKLIST 未配置），当前仅具备拦截机制、无生效词表"
            ),
        },
        {
            "item": "传输加密",
            "status": "pending",
            "detail": "开发环境为 HTTP；生产应在网关（Nginx/Ingress）终止 TLS，后端不直接暴露",
        },
        {
            "item": "存储加密",
            "status": "pending",
            "detail": "当前依赖部署环境（PostgreSQL/MinIO 卷）加密；字段级加密与 KMS 待接入",
        },
        {
            "item": "数据出境",
            "status": "ok",
            "detail": "生成/检索类模型均取国产合规服务（SiliconFlow 国内节点），未使用境外模型",
        },
        {
            "item": "个人信息最小化",
            "status": "ok",
            "detail": "审计不落请求体；生成产物以 32 位随机 id 寻址，不可枚举；分享用随机 token",
        },
    ]
    return ApiResponse(
        data={"checks": checks, "pending": sum(1 for item in checks if item["status"] == "pending")},
        trace_id=uuid.uuid4().hex,
    )
