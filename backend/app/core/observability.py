"""工单20 · 全链路可观测与审计

工单编号：人工智能CV-AIGC-20-文旅Agent任务工单-功能集成测试与部署
对应 docs/06 §六「统一 trace_id 贯穿全链路，便于测试与排障」与
        docs/01 §七「操作日志 + 访问日志，满足审计追溯」。

三件事：
  1. **trace_id 贯穿**：中间件为每个请求生成/透传 trace_id 存入 ContextVar，
     响应体与响应头、访问日志、审计记录、异常日志全部用它对齐，排障时一个 id 串到底。
  2. **访问日志**：每个请求记录方法、路径、状态码、耗时、来源 IP（脱敏后）。
  3. **操作审计**：对状态变更类请求（POST/PUT/PATCH/DELETE）落审计记录，
     失败不阻断业务。
"""
from __future__ import annotations

import contextvars
import logging
import re
import time
import uuid
from typing import Any

logger = logging.getLogger("wenlv.audit")

# 请求级 trace_id；在异步/多线程下由 ContextVar 保证隔离
_trace_id: contextvars.ContextVar[str] = contextvars.ContextVar("wenlv_trace_id", default="")

TRACE_HEADER = "X-Trace-Id"

# 状态变更方法才计入操作审计（GET 属访问日志范畴，不落库以避免表膨胀）
AUDIT_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# 敏感信息脱敏：日志与审计中不得出现完整手机号、证件号、邮箱
_PHONE = re.compile(r"(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)")
_ID_CARD = re.compile(r"(?<!\d)(\d{6})\d{8}(\d{3}[\dXx])(?!\d)")
_EMAIL = re.compile(r"([\w.+-]{1,3})[\w.+-]*(@[\w-]+\.[\w.]+)")


def new_trace_id() -> str:
    return uuid.uuid4().hex[:16]


def set_trace_id(value: str) -> contextvars.Token:
    return _trace_id.set(value)


def reset_trace_id(token: contextvars.Token) -> None:
    try:
        _trace_id.reset(token)
    except ValueError:  # token 跨上下文复用时会抛错，忽略即可
        pass


def get_trace_id() -> str:
    return _trace_id.get() or ""


def mask_sensitive(text: str) -> str:
    """对日志文本做脱敏：手机号 / 证件号 / 邮箱。

    docs/06 §4.5 要求「敏感数据脱敏与匿名化处理」，日志是泄露风险最高的一环
    （常被整份导出），因此进入日志前统一过一遍。
    """
    if not text:
        return text
    text = _PHONE.sub(r"\1****\2", text)
    text = _ID_CARD.sub(r"\1********\2", text)
    text = _EMAIL.sub(r"\1***\2", text)
    return text


def mask_ip(ip: str) -> str:
    """来源 IP 脱敏：IPv4 保留网段，IPv6 保留前 4 段。"""
    if not ip:
        return ""
    if ":" in ip:
        return ":".join(ip.split(":")[:4]) + "::"
    parts = ip.split(".")
    return ".".join(parts[:3] + ["*"]) if len(parts) == 4 else ip


class Stopwatch:
    """请求耗时计时器（毫秒）。"""

    def __init__(self) -> None:
        self._start = time.perf_counter()

    @property
    def ms(self) -> float:
        return round((time.perf_counter() - self._start) * 1000, 2)


def log_access(method: str, path: str, status: int, elapsed_ms: float, client_ip: str) -> None:
    """访问日志：单行结构化，便于 Loki/ELK 采集（docs/01 §六 日志）。"""
    logger.info(
        "access method=%s path=%s status=%d cost_ms=%.2f ip=%s trace_id=%s",
        method,
        mask_sensitive(path),
        status,
        elapsed_ms,
        mask_ip(client_ip),
        get_trace_id(),
    )


def record_audit(method: str, path: str, status: int, client_ip: str, role: str = "guest") -> None:
    """操作审计：状态变更类请求落库，失败只告警不阻断。

    不记录请求体：游客上传的照片与文本属个人信息，审计只保留
    「谁在何时对哪个资源做了什么、结果如何」。
    """
    if method.upper() not in AUDIT_METHODS:
        return
    try:
        from ..db.base import SessionLocal
        from ..db.models import AuditLog

        with SessionLocal() as db:
            db.add(
                AuditLog(
                    method=method.upper(),
                    path=path[:256],
                    status=status,
                    client_ip=mask_ip(client_ip),
                    role=role,
                    trace_id=get_trace_id(),
                )
            )
            db.commit()
    except Exception as exc:  # 审计组件故障不得影响业务
        logger.warning("审计记录写入失败：%s: %s", type(exc).__name__, exc)


def snapshot() -> dict[str, Any]:
    """当前请求的可观测上下文，供 readyz / 排障接口回显。"""
    return {"trace_id": get_trace_id()}
