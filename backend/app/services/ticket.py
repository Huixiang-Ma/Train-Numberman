"""docs/09 G3 · 票务服务（批次 5）

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成

边界（docs/09 §3.2）：到「订单闭环 + 核销」为止，**不含支付通道与资金结算**。
`pay()` 是**支付占位**：只把订单推进到已支付并签发电子票，不产生任何资金动作。
接入真实通道时替换本方法内部实现即可，表结构与状态机不变。

库存一致性是本模块的核心：下单用**单条条件更新**完成"检查余量 + 扣减"，
不做"先 SELECT 再 UPDATE"，因为后者在两个请求同时到达时会双卖同一张余票。
"""
from __future__ import annotations

import logging
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select, update

from ..db.base import SessionLocal
from ..db.models import DigitalTicket, Park, TicketOrder, TicketSlot, TicketType

logger = logging.getLogger(__name__)

# 订单状态机：pending → paid → checked_in / refunding → refunded / cancelled
ORDER_STATUS_LABEL = {
    "pending": "待支付",
    "paid": "待使用",
    "checked_in": "已核销",
    "refunding": "退款中",
    "refunded": "已退款",
    "cancelled": "已取消",
}

TICKET_STATUS_LABEL = {
    "valid": "有效",
    "checked_in": "已核销",
    "expired": "已过期",
    "refunded": "已退票",
}

# 单笔最大购票数：既是业务限制，也是防止一次请求把某个时段的库存整体占满
MAX_QUANTITY = 50


class TicketService:
    """票种 / 时段 / 订单 / 电子票 的读写服务。"""

    # ------------------------------------------------------------ 票种与时段

    def park_tickets(self, park_id: str, days: int = 7) -> dict | None:
        """景区可售票种，并为每个票种带上未来若干天的可售时段。

        只返回 `today` 起的时段：过期时段对游客无意义，返回它们会让日期选择器
        默认落在一个不可选的日期上。
        """
        with SessionLocal() as db:
            park = db.get(Park, park_id)
            if park is None:
                return None

            types = db.scalars(
                select(TicketType).where(TicketType.park_id == park_id).order_by(TicketType.price_cents)
            ).all()
            today = date.today()
            horizon = today + timedelta(days=days)
            slots = (
                db.scalars(
                    select(TicketSlot)
                    .where(
                        TicketSlot.ticket_type_id.in_([item.id for item in types]) if types else False,
                        TicketSlot.slot_date >= today,
                        TicketSlot.slot_date <= horizon,
                    )
                    .order_by(TicketSlot.slot_date, TicketSlot.start_time)
                ).all()
                if types
                else []
            )

            by_type: dict[str, list] = {}
            for slot in slots:
                by_type.setdefault(slot.ticket_type_id, []).append(self._slot_dict(slot))

            return {
                "park": {"id": park.id, "name": park.name, "level": park.level, "ticket_notice": park.ticket_notice},
                "ticket_types": [
                    {**self._type_dict(item), "slots": by_type.get(item.id, [])} for item in types
                ],
                "days": days,
            }

    def create_type(
        self,
        *,
        park_id: str,
        name: str,
        category: str = "adult",
        price_cents: int = 0,
        refundable: bool = True,
        valid_days: int = 1,
        notice: str = "",
        total_days: int = 7,
        daily_inventory: int = 0,
    ) -> dict:
        """新建票种，并按需一次性铺开未来若干天的时段。

        为什么建票种时就铺时段：票种建好却没有时段，游客端会显示"暂无可售日期"，
        运营还得再去另一个页面补一轮。默认一起做，需要精细控制时 total_days 传 0 跳过。
        """
        with SessionLocal() as db:
            row = TicketType(
                id=uuid.uuid4().hex,
                park_id=park_id,
                name=name,
                category=category,
                price_cents=max(0, int(price_cents)),
                refundable=refundable,
                valid_days=max(1, int(valid_days)),
                notice=notice,
                status="on_sale",
            )
            db.add(row)
            db.flush()

            if total_days > 0:
                today = date.today()
                for offset in range(total_days):
                    db.add(
                        TicketSlot(
                            id=uuid.uuid4().hex,
                            ticket_type_id=row.id,
                            slot_date=today + timedelta(days=offset),
                            start_time="08:00",
                            end_time="17:00",
                            inventory=max(0, int(daily_inventory)),
                            sold=0,
                        )
                    )
            db.commit()
            db.refresh(row)
            return self._type_dict(row)

    def update_type(self, ticket_type_id: str, patch: dict) -> dict | None:
        with SessionLocal() as db:
            row = db.get(TicketType, ticket_type_id)
            if row is None:
                return None
            for field in ("name", "category", "notice", "status"):
                if patch.get(field) is not None:
                    setattr(row, field, patch[field])
            if patch.get("price_cents") is not None:
                row.price_cents = max(0, int(patch["price_cents"]))
            if patch.get("refundable") is not None:
                row.refundable = bool(patch["refundable"])
            if patch.get("valid_days") is not None:
                row.valid_days = max(1, int(patch["valid_days"]))
            db.commit()
            db.refresh(row)
            return self._type_dict(row)

    def set_slot_inventory(self, slot_id: str, inventory: int) -> dict | None:
        """调整某时段的库存上限。

        不允许把上限设到已售数量之下：那会让"已售 > 库存"成为一个恒不可售的脏状态，
        后续所有下单都返回余票不足，而运营从界面上看不出原因。
        """
        with SessionLocal() as db:
            row = db.get(TicketSlot, slot_id)
            if row is None:
                return None
            if inventory < row.sold:
                raise ValueError(f"库存不能低于已售 {row.sold} 张")
            row.inventory = max(0, int(inventory))
            db.commit()
            db.refresh(row)
            return self._slot_dict(row)

    def list_slots(self, ticket_type_id: str, days: int = 14) -> list[dict]:
        with SessionLocal() as db:
            today = date.today()
            rows = db.scalars(
                select(TicketSlot)
                .where(
                    TicketSlot.ticket_type_id == ticket_type_id,
                    TicketSlot.slot_date >= today,
                    TicketSlot.slot_date <= today + timedelta(days=days),
                )
                .order_by(TicketSlot.slot_date, TicketSlot.start_time)
            ).all()
            return [self._slot_dict(row) for row in rows]

    # ------------------------------------------------------------------ 下单

    def create_order(
        self,
        *,
        park_id: str,
        ticket_type_id: str,
        slot_id: str,
        quantity: int,
        visitor_ref: str,
        contact_name: str = "",
        contact_phone: str = "",
    ) -> tuple[dict | None, str | None]:
        """下单并占库存。返回 (订单, 错误原因)，二者必有其一为 None。"""
        quantity = int(quantity)
        if quantity < 1 or quantity > MAX_QUANTITY:
            return None, f"购票数量需在 1~{MAX_QUANTITY} 之间"

        with SessionLocal() as db:
            ticket_type = db.get(TicketType, ticket_type_id)
            if ticket_type is None or ticket_type.park_id != park_id:
                return None, "票种不存在或不属于该景区"
            if ticket_type.status != "on_sale":
                return None, "该票种已下架"

            slot = db.get(TicketSlot, slot_id)
            if slot is None or slot.ticket_type_id != ticket_type_id:
                return None, "时段不存在"
            if slot.slot_date < date.today():
                return None, "所选时段已过期"

            # 关键：单条 SQL 完成「检查余量 + 扣减」。
            # 若改成先 SELECT 余量再 UPDATE，两个并发请求会同时读到"还剩 1 张"并各自扣减，
            # 结果是超卖。条件更新把判断下推到数据库，rowcount 为 0 即表示余量不足。
            claimed = db.execute(
                update(TicketSlot)
                .where(
                    TicketSlot.id == slot_id,
                    (TicketSlot.inventory - TicketSlot.sold) >= quantity,
                )
                .values(sold=TicketSlot.sold + quantity)
            ).rowcount
            if not claimed:
                db.rollback()
                fresh = db.get(TicketSlot, slot_id)
                remain = max(0, (fresh.inventory - fresh.sold)) if fresh else 0
                return None, f"余票不足，该时段仅剩 {remain} 张"

            order = TicketOrder(
                id=uuid.uuid4().hex,
                order_no=self._order_no(),
                visitor_ref=visitor_ref or "",
                park_id=park_id,
                ticket_type_id=ticket_type_id,
                slot_id=slot_id,
                quantity=quantity,
                amount_cents=int(ticket_type.price_cents) * quantity,
                contact_name=contact_name,
                contact_phone=contact_phone,
                status="pending",
            )
            db.add(order)
            db.commit()
            db.refresh(order)
            return self._order_dict(order, db), None

    def pay(self, order_id: str, payment_ref: str = "") -> tuple[dict | None, str | None]:
        """支付占位：推进到已支付并签发电子票。

        **不产生资金动作**（见模块顶部边界声明）。真正接入支付通道时，
        应在通道回调里调用本方法，而不是由前端直接调用。
        """
        with SessionLocal() as db:
            order = db.get(TicketOrder, order_id)
            if order is None:
                return None, "订单不存在"
            if order.status == "paid":
                return self._order_dict(order, db), None
            if order.status != "pending":
                return None, f"当前状态（{ORDER_STATUS_LABEL.get(order.status, order.status)}）不可支付"

            order.status = "paid"
            order.paid_at = datetime.now(timezone.utc)
            order.payment_ref = payment_ref or f"PLACEHOLDER-{secrets.token_hex(6).upper()}"

            # 一单一票：每张票独立核销，因此必须在支付时拆成 quantity 张，
            # 否则 3 人同行会被当成一张票、核销一次就把三人一起放进去。
            for _ in range(order.quantity):
                db.add(
                    DigitalTicket(
                        id=uuid.uuid4().hex,
                        order_id=order.id,
                        code=self._ticket_code(),
                        # 二维码只编码随机 token，不含订单信息：票面被拍照外传时
                        # 不会顺带泄露手机号等个人信息
                        qr_payload=secrets.token_urlsafe(16),
                        status="valid",
                    )
                )
            db.commit()
            db.refresh(order)
            return self._order_dict(order, db), None

    def cancel(self, order_id: str) -> tuple[dict | None, str | None]:
        """取消待支付订单并**释放已占库存**。

        不释放会让库存被"僵尸订单"永久占住：用户下单不付款就走了，
        那个时段的余票就再也卖不出去。
        """
        with SessionLocal() as db:
            order = db.get(TicketOrder, order_id)
            if order is None:
                return None, "订单不存在"
            if order.status == "cancelled":
                return self._order_dict(order, db), None
            if order.status != "pending":
                return None, "仅待支付订单可取消"

            db.execute(
                update(TicketSlot)
                .where(TicketSlot.id == order.slot_id)
                .values(sold=func.greatest(TicketSlot.sold - order.quantity, 0))
            )
            order.status = "cancelled"
            order.cancelled_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(order)
            return self._order_dict(order, db), None

    def refund(self, order_id: str, reason: str = "") -> tuple[dict | None, str | None]:
        """退款：作废电子票并释放库存。同样**不含资金动作**。"""
        with SessionLocal() as db:
            order = db.get(TicketOrder, order_id)
            if order is None:
                return None, "订单不存在"
            if order.status == "refunded":
                return self._order_dict(order, db), None
            if order.status not in ("paid", "checked_in"):
                return None, "仅已支付或已核销订单可申请退款"

            tickets = db.scalars(select(DigitalTicket).where(DigitalTicket.order_id == order.id)).all()
            if any(item.status == "checked_in" for item in tickets):
                return None, "订单中已有票券核销，不可退款"

            for item in tickets:
                item.status = "refunded"

            db.execute(
                update(TicketSlot)
                .where(TicketSlot.id == order.slot_id)
                .values(sold=func.greatest(TicketSlot.sold - order.quantity, 0))
            )
            order.status = "refunded"
            order.refunded_at = datetime.now(timezone.utc)
            order.cancel_reason = reason
            db.commit()
            db.refresh(order)
            return self._order_dict(order, db), None

    # ------------------------------------------------------------------ 核销

    def check_in(self, credential: str, gate: str = "") -> tuple[dict | None, str | None]:
        """核销电子票。credential 可以是票号（人工输入）或二维码 token（扫码）。

        「防重复入园」是本方法的第一职责：已核销的票再扫必须被拒，
        并且要如实告诉闸口人员**上次核销的时间与闸口**，否则现场无法判断
        是游客重复排队还是票被复制使用。
        """
        credential = (credential or "").strip()
        if not credential:
            return None, "请提供票号或二维码内容"

        with SessionLocal() as db:
            ticket = db.scalars(
                select(DigitalTicket).where(
                    (DigitalTicket.code == credential) | (DigitalTicket.qr_payload == credential)
                )
            ).first()
            if ticket is None:
                return None, "票号无效"

            if ticket.status == "checked_in":
                when = ticket.checked_in_at.strftime("%m-%d %H:%M") if ticket.checked_in_at else "此前"
                where = ticket.gate or "未知闸口"
                return None, f"该票已于 {when} 在「{where}」核销，不可重复入园"
            if ticket.status == "refunded":
                return None, "该票已退款，不可入园"
            if ticket.status == "expired":
                return None, "该票已过期"

            order = db.get(TicketOrder, ticket.order_id)
            if order is None:
                return None, "订单不存在"
            if order.status == "pending":
                return None, "订单尚未支付"

            now = datetime.now(timezone.utc)
            ticket.status = "checked_in"
            ticket.checked_in_at = now
            ticket.gate = gate or "默认闸口"

            # 只有当订单下**所有**票都核销完，订单才算已核销。
            # 否则 3 人同行核销第 1 张就把整单标记为已核销，后两张的核销状态无从追溯。
            siblings = db.scalars(select(DigitalTicket).where(DigitalTicket.order_id == order.id)).all()
            if all(item.status == "checked_in" for item in siblings):
                order.status = "checked_in"
                order.checked_in_at = now

            db.commit()
            remaining = sum(1 for item in siblings if item.status == "valid")
            return (
                {
                    "code": ticket.code,
                    "status": ticket.status,
                    "checked_in_at": now.isoformat(),
                    "gate": ticket.gate,
                    "order_no": order.order_no,
                    "order_status": order.status,
                    "order_status_label": ORDER_STATUS_LABEL.get(order.status, order.status),
                    "remaining_in_order": remaining,
                },
                None,
            )

    # ------------------------------------------------------------------ 查询

    def slot_context(self, slot_id: str) -> dict | None:
        """由时段 id 反查「景区 + 票种 + 时段」。

        用于 `/booking/:slotId` 这类深链：运营发出去的链接往往只带一个时段 id，
        页面得据此还原出完整的下单上下文，否则深链只能落在首页让用户重新找。
        """
        with SessionLocal() as db:
            slot = db.get(TicketSlot, slot_id)
            if slot is None:
                return None
            ticket_type = db.get(TicketType, slot.ticket_type_id)
            if ticket_type is None:
                return None
            park = db.get(Park, ticket_type.park_id)
            return {
                "park": {"id": park.id, "name": park.name, "level": park.level} if park else None,
                "ticket_type": self._type_dict(ticket_type),
                "slot": self._slot_dict(slot),
            }

    def qr_credential(self, ticket_id: str) -> dict | None:
        """取某张电子票的二维码载荷。

        单独开一个只读方法而不是复用 get_order：二维码端点每次刷新都会调用，
        走订单聚合会顺带查出票种、时段、景区三个对象，白白多三次查询。
        """
        with SessionLocal() as db:
            row = db.get(DigitalTicket, ticket_id)
            if row is None:
                return None
            return {
                "id": row.id,
                "code": row.code,
                # 二维码内容优先用随机 token；历史数据若为空则退回票号，
                # 避免旧票因缺 token 而无法出码
                "payload": row.qr_payload or row.code,
                "status": row.status,
            }

    def get_order(self, order_id: str) -> dict | None:
        with SessionLocal() as db:
            row = db.get(TicketOrder, order_id)
            return self._order_dict(row, db) if row else None

    def get_order_by_no(self, order_no: str) -> dict | None:
        with SessionLocal() as db:
            row = db.scalars(select(TicketOrder).where(TicketOrder.order_no == order_no)).first()
            return self._order_dict(row, db) if row else None

    def list_orders(self, visitor_ref: str = "", limit: int = 50) -> list[dict]:
        """我的订单：按匿名 visitor_ref 归集（本项目无游客账号体系）。"""
        with SessionLocal() as db:
            stmt = select(TicketOrder)
            if visitor_ref:
                stmt = stmt.where(TicketOrder.visitor_ref == visitor_ref)
            rows = db.scalars(stmt.order_by(TicketOrder.created_at.desc()).limit(limit)).all()
            return [self._order_dict(row, db) for row in rows]

    def admin_orders(
        self,
        *,
        park_id: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        with SessionLocal() as db:
            stmt = select(TicketOrder)
            if park_id:
                stmt = stmt.where(TicketOrder.park_id == park_id)
            if status:
                stmt = stmt.where(TicketOrder.status == status)
            if keyword:
                # 支持按订单号或联系人检索：现场客服最常用的两个入口
                like = f"%{keyword.strip()}%"
                stmt = stmt.where(TicketOrder.order_no.ilike(like) | TicketOrder.contact_name.ilike(like))
            rows = db.scalars(stmt.order_by(TicketOrder.created_at.desc()).limit(limit)).all()
            return [self._order_dict(row, db) for row in rows]

    def stats(self, park_id: str | None = None) -> dict:
        """经营汇总：订单量、核销率、销售额。

        只统计 `paid` 及之后的订单为"已成交"：待支付订单的金额还不是收入，
        把它算进来会让看板虚高。
        """
        with SessionLocal() as db:
            base = select(func.count()).select_from(TicketOrder)
            if park_id:
                base = base.where(TicketOrder.park_id == park_id)

            total = int(db.scalar(base) or 0)
            paid_like = ("paid", "checked_in")
            paid_count = int(db.scalar(base.where(TicketOrder.status.in_(paid_like))) or 0)
            checked_count = int(db.scalar(base.where(TicketOrder.status == "checked_in")) or 0)
            pending_count = int(db.scalar(base.where(TicketOrder.status == "pending")) or 0)
            refunded_count = int(db.scalar(base.where(TicketOrder.status == "refunded")) or 0)

            revenue = select(func.coalesce(func.sum(TicketOrder.amount_cents), 0))
            if park_id:
                revenue = revenue.where(TicketOrder.park_id == park_id)
            revenue_cents = int(db.scalar(revenue.where(TicketOrder.status.in_(paid_like))) or 0)

            tickets = select(func.coalesce(func.sum(TicketOrder.quantity), 0))
            if park_id:
                tickets = tickets.where(TicketOrder.park_id == park_id)
            ticket_count = int(db.scalar(tickets.where(TicketOrder.status.in_(paid_like))) or 0)

            checked_tickets = select(func.count()).select_from(DigitalTicket).where(
                DigitalTicket.status == "checked_in"
            )
            checked_tickets_count = int(db.scalar(checked_tickets) or 0)

            return {
                "orders_total": total,
                "orders_pending": pending_count,
                "orders_paid": paid_count,
                "orders_checked_in": checked_count,
                "orders_refunded": refunded_count,
                "tickets_sold": ticket_count,
                "tickets_checked_in": checked_tickets_count,
                "amount_cents": revenue_cents,
                # 核销率分母用已成交订单数而不是总订单数，否则待支付订单会压低这个比率、
                # 让运营误判现场核销效率
                "checkin_rate": round(checked_count / paid_count, 4) if paid_count else 0.0,
            }

    # ------------------------------------------------------------- 行 → dict

    @staticmethod
    def _order_no() -> str:
        """订单号：日期 + 随机段。用随机而不是自增，避免订单总量被外部枚举推算。"""
        return f"WL{datetime.now().strftime('%Y%m%d')}{secrets.token_hex(4).upper()}"

    @staticmethod
    def _ticket_code() -> str:
        return f"T{secrets.token_hex(6).upper()}"

    @staticmethod
    def _type_dict(row: TicketType) -> dict:
        return {
            "id": row.id,
            "park_id": row.park_id,
            "name": row.name,
            "category": row.category,
            "price_cents": row.price_cents,
            "price": round(row.price_cents / 100, 2),
            "currency": row.currency,
            "refundable": row.refundable,
            "valid_days": row.valid_days,
            "notice": row.notice,
            "status": row.status,
        }

    @staticmethod
    def _slot_dict(row: TicketSlot) -> dict:
        return {
            "id": row.id,
            "ticket_type_id": row.ticket_type_id,
            "slot_date": row.slot_date.isoformat() if row.slot_date else None,
            "start_time": row.start_time,
            "end_time": row.end_time,
            "inventory": row.inventory,
            "sold": row.sold,
            "remaining": max(0, row.inventory - row.sold),
            "sold_out": row.sold >= row.inventory,
        }

    def _order_dict(self, row: TicketOrder, db) -> dict:
        ticket_type = db.get(TicketType, row.ticket_type_id)
        slot = db.get(TicketSlot, row.slot_id)
        park = db.get(Park, row.park_id)
        tickets = db.scalars(
            select(DigitalTicket).where(DigitalTicket.order_id == row.id).order_by(DigitalTicket.code)
        ).all()
        return {
            "id": row.id,
            "order_no": row.order_no,
            "visitor_ref": row.visitor_ref,
            "park_id": row.park_id,
            "park_name": park.name if park else "",
            "ticket_type_id": row.ticket_type_id,
            "ticket_type_name": ticket_type.name if ticket_type else "",
            "ticket_category": ticket_type.category if ticket_type else "",
            "slot_id": row.slot_id,
            "slot_date": slot.slot_date.isoformat() if slot and slot.slot_date else None,
            "slot_start": slot.start_time if slot else "",
            "slot_end": slot.end_time if slot else "",
            "quantity": row.quantity,
            "amount_cents": row.amount_cents,
            "amount": round(row.amount_cents / 100, 2),
            "contact_name": row.contact_name,
            # 手机号脱敏后输出：订单列表会被客服与运营看到，无需明文
            "contact_phone": _mask_phone(row.contact_phone),
            "status": row.status,
            "status_label": ORDER_STATUS_LABEL.get(row.status, row.status),
            "payment_ref": row.payment_ref,
            "booked_at": row.booked_at.isoformat() if row.booked_at else None,
            "paid_at": row.paid_at.isoformat() if row.paid_at else None,
            "checked_in_at": row.checked_in_at.isoformat() if row.checked_in_at else None,
            "refunded_at": row.refunded_at.isoformat() if row.refunded_at else None,
            "cancel_reason": row.cancel_reason,
            "tickets": [
                {
                    "id": item.id,
                    "code": item.code,
                    "qr_payload": item.qr_payload,
                    "status": item.status,
                    "status_label": TICKET_STATUS_LABEL.get(item.status, item.status),
                    "gate": item.gate,
                    "checked_in_at": item.checked_in_at.isoformat() if item.checked_in_at else None,
                }
                for item in tickets
            ],
        }


def _mask_phone(phone: str) -> str:
    """手机号脱敏：保留前 3 后 2，中间定长掩码。"""
    digits = (phone or "").strip()
    if len(digits) < 7:
        return digits
    return f"{digits[:3]}****{digits[-2:]}"
