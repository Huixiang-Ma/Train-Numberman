"""docs/09 G3 · 票务接口（批次 5）

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成

权限划分依据 docs/09 §2.1 的角色表：
  - **游客侧**（查票种、下单、支付占位、取消、我的订单、看电子票）不挂 RBAC，
    与本项目其它公开接口一致的理由：游客端未登录也必须能走完购票流程。
  - **票务/闸口侧**（核销、订单管理、票种与库存维护、退款审核）挂 require_editor，
    对应「票务/闸口人员」角色。

路由顺序：本文件所有路径的**首段都是字面量**（park / slots / qr / order / orders /
checkin / admin），不存在 `/ticket/{x}` 这类裸参数路由，因此 FastAPI 的声明顺序
不会造成误匹配。
"""
from __future__ import annotations

import io
import uuid

import qrcode
from fastapi import APIRouter, Depends, HTTPException, Query, Response

from ...schemas import (
    ApiResponse,
    OrderCreateRequest,
    RefundRequest,
    SlotPatch,
    TicketCheckinRequest,
    TicketTypePatch,
    TicketTypeRequest,
)
from ...services.ticket import TicketService
from ..deps import require_editor

router = APIRouter(prefix="/ticket", tags=["ticket"])


# ---------------------------------------------------------------- 游客侧（公开）

@router.get("/park/{park_id}", response_model=ApiResponse)
def park_tickets(park_id: str, days: int = Query(7, ge=1, le=30)) -> ApiResponse:
    """景区可售票种与未来若干天的可售时段。"""
    data = TicketService().park_tickets(park_id, days=days)
    if data is None:
        raise HTTPException(status_code=404, detail="景区不存在")
    return ApiResponse(data=data, trace_id=uuid.uuid4().hex)


@router.get("/slots/{ticket_type_id}", response_model=ApiResponse)
def list_slots(ticket_type_id: str, days: int = Query(14, ge=1, le=60)) -> ApiResponse:
    items = TicketService().list_slots(ticket_type_id, days=days)
    return ApiResponse(data={"items": items, "total": len(items)}, trace_id=uuid.uuid4().hex)


@router.get("/slot/{slot_id}", response_model=ApiResponse)
def slot_context(slot_id: str) -> ApiResponse:
    """由时段 id 反查景区 / 票种 / 时段，供 /booking/:slotId 深链还原下单上下文。"""
    data = TicketService().slot_context(slot_id)
    if data is None:
        raise HTTPException(status_code=404, detail="时段不存在")
    return ApiResponse(data=data, trace_id=uuid.uuid4().hex)


@router.get("/qr/{ticket_id}")
def ticket_qr(ticket_id: str) -> Response:
    """电子票二维码（PNG，按需生成）。

    由后端现算而不是预先生成存图：二维码内容就是票的随机 token，
    每张票的码在有效期内不会变，缓存即可；而存图会引入"图与票不同步"的清理负担。

    载荷只含随机 token，**不含订单号、手机号**：票面二维码常被游客拍照发到社交平台，
    编码业务信息等于顺带泄露个人信息。
    """
    credential = TicketService().qr_credential(ticket_id)
    if credential is None:
        raise HTTPException(status_code=404, detail="电子票不存在")

    image = qrcode.make(credential["payload"])
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return Response(
        content=buffer.getvalue(),
        media_type="image/png",
        # private：票码属个人凭证，不应被中间代理缓存
        headers={"Cache-Control": "private, max-age=1800"},
    )


@router.post("/order", response_model=ApiResponse)
def create_order(payload: OrderCreateRequest) -> ApiResponse:
    """下单占库存。余票不足时返回 409 而不是 400：
    这是**冲突**（并发争用同一份库存）而不是请求格式错误，前端据此区分提示文案。"""
    order, error = TicketService().create_order(
        park_id=payload.park_id,
        ticket_type_id=payload.ticket_type_id,
        slot_id=payload.slot_id,
        quantity=payload.quantity,
        visitor_ref=payload.visitor_ref,
        contact_name=payload.contact_name,
        contact_phone=payload.contact_phone,
    )
    if error:
        raise HTTPException(status_code=409, detail=error)
    return ApiResponse(data=order, trace_id=uuid.uuid4().hex)


@router.get("/orders", response_model=ApiResponse)
def my_orders(visitor_ref: str = "", limit: int = Query(50, ge=1, le=200)) -> ApiResponse:
    """我的订单。visitor_ref 为空则返回全部（该分支供管理端之外的调试使用）。"""
    items = TicketService().list_orders(visitor_ref=visitor_ref, limit=limit)
    return ApiResponse(data={"items": items, "total": len(items)}, trace_id=uuid.uuid4().hex)


@router.get("/order/{order_id}", response_model=ApiResponse)
def get_order(order_id: str) -> ApiResponse:
    order = TicketService().get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")
    return ApiResponse(data=order, trace_id=uuid.uuid4().hex)


@router.post("/order/{order_id}/pay", response_model=ApiResponse)
def pay_order(order_id: str) -> ApiResponse:
    """支付占位（docs/09 §3.2 边界声明）：推进状态并签发电子票，**不产生资金动作**。

    生产环境必须改由支付通道回调触发，不能保留这个前端可直接调用的入口。
    """
    order, error = TicketService().pay(order_id)
    if error:
        raise HTTPException(status_code=409, detail=error)
    return ApiResponse(data=order, trace_id=uuid.uuid4().hex)


@router.post("/order/{order_id}/cancel", response_model=ApiResponse)
def cancel_order(order_id: str) -> ApiResponse:
    order, error = TicketService().cancel(order_id)
    if error:
        raise HTTPException(status_code=409, detail=error)
    return ApiResponse(data=order, trace_id=uuid.uuid4().hex)


# ---------------------------------------------------------------- 票务/闸口侧

@router.post("/checkin", response_model=ApiResponse)
def check_in(payload: TicketCheckinRequest, _=Depends(require_editor)) -> ApiResponse:
    """核销。失败（含"重复入园"）一律返回 409 并给出可读原因。"""
    result, error = TicketService().check_in(payload.credential, gate=payload.gate)
    if error:
        raise HTTPException(status_code=409, detail=error)
    return ApiResponse(data=result, trace_id=uuid.uuid4().hex)


@router.post("/order/{order_id}/refund", response_model=ApiResponse)
def refund_order(order_id: str, payload: RefundRequest, _=Depends(require_editor)) -> ApiResponse:
    """退款审核（运营动作）。同样不含资金动作。"""
    order, error = TicketService().refund(order_id, reason=payload.reason)
    if error:
        raise HTTPException(status_code=409, detail=error)
    return ApiResponse(data=order, trace_id=uuid.uuid4().hex)


@router.get("/admin/orders", response_model=ApiResponse)
def admin_orders(
    park_id: str | None = None,
    status: str | None = None,
    keyword: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    _=Depends(require_editor),
) -> ApiResponse:
    items = TicketService().admin_orders(park_id=park_id, status=status, keyword=keyword, limit=limit)
    return ApiResponse(data={"items": items, "total": len(items)}, trace_id=uuid.uuid4().hex)


@router.get("/admin/stats", response_model=ApiResponse)
def ticket_stats(park_id: str | None = None, _=Depends(require_editor)) -> ApiResponse:
    return ApiResponse(data=TicketService().stats(park_id=park_id), trace_id=uuid.uuid4().hex)


@router.post("/admin/types", response_model=ApiResponse)
def create_type(payload: TicketTypeRequest, _=Depends(require_editor)) -> ApiResponse:
    data = TicketService().create_type(
        park_id=payload.park_id,
        name=payload.name,
        category=payload.category,
        price_cents=payload.price_cents,
        refundable=payload.refundable,
        valid_days=payload.valid_days,
        notice=payload.notice,
        total_days=payload.total_days,
        daily_inventory=payload.daily_inventory,
    )
    return ApiResponse(data=data, trace_id=uuid.uuid4().hex)


@router.put("/admin/types/{ticket_type_id}", response_model=ApiResponse)
def update_type(ticket_type_id: str, payload: TicketTypePatch, _=Depends(require_editor)) -> ApiResponse:
    data = TicketService().update_type(ticket_type_id, payload.model_dump(exclude_none=True))
    if data is None:
        raise HTTPException(status_code=404, detail="票种不存在")
    return ApiResponse(data=data, trace_id=uuid.uuid4().hex)


@router.put("/admin/slots/{slot_id}", response_model=ApiResponse)
def update_slot(slot_id: str, payload: SlotPatch, _=Depends(require_editor)) -> ApiResponse:
    try:
        data = TicketService().set_slot_inventory(slot_id, payload.inventory)
    except ValueError as exc:
        # 库存不能低于已售是可预期的业务拒绝，用 409 而不是 500
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if data is None:
        raise HTTPException(status_code=404, detail="时段不存在")
    return ApiResponse(data=data, trace_id=uuid.uuid4().hex)
