"""docs/09 G3 · 票务与游客服务行为验证（长期脚本）

工单编号：人工智能CV-AIGC-20-文旅Agent任务工单-功能集成测试与部署

为什么这个脚本必须长期保留：它验证的是全项目**最不能出错**的两条业务不变量 ——
  · **防超卖**：并发争用同一份余票时不得卖出超过库存
  · **防重复入园**：同一张电子票不得核销两次，且必须能说明上次核销的时间与闸口
这两条一旦失效，后果是现场冲突与经济纠纷，而不是界面瑕疵。前端测试只能验证
界面契约，碰不到这两条；因此需要一个能重复执行的端到端脚本。

三条实现纪律（都是踩过坑之后加的）：
  1. **不假设干净初始状态**。脚本会被反复执行，上一轮的已售量还在。
     因此库存相关的断言一律基于"当前已售量"推算，而不是假设从 0 开始。
  2. **不提供"重置已售"的旁路**。篡改 sold 会让库存与订单对不上账；
     造场景的办法是"把库存设成 sold+N"，而不是改 sold。
  3. **鉴权用例与业务用例分开**。核销/退款属 require_editor，必须带令牌；
     未带令牌的那几条专门用来验证 RBAC 真的生效。

用法：python scripts/verify_ticket.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BASE = "http://127.0.0.1:8100/api/v1"
FAILURES: list[str] = []
TOKEN = ""

# Windows 控制台默认使用 GBK，直接 print("✓") 会抛 UnicodeEncodeError 并**中断整个脚本** ——
# 一个"检查项还没跑完就崩了"的验证脚本比没有脚本更糟。因此先把 stdout 切到 UTF-8；
# 若环境不支持 reconfigure，则退回纯 ASCII 标记，保证任何终端都能跑完。
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    MARK_OK, MARK_BAD = "✓", "✗"
except Exception:
    MARK_OK, MARK_BAD = "OK", "X"


def call(method: str, path: str, auth: bool = False, **kwargs):
    headers = dict(kwargs.pop("headers", {}))
    if auth:
        headers["Authorization"] = f"Bearer {TOKEN}"
    response = httpx.request(method, BASE + path, timeout=90, headers=headers, **kwargs)
    try:
        return response.status_code, response.json()
    except Exception:
        return response.status_code, None


def check(label: str, condition: bool, detail: str = "") -> None:
    print(f"   {MARK_OK if condition else MARK_BAD} {label}{('  ' + detail) if detail else ''}")
    if not condition:
        FAILURES.append(label)


def slot_of(ticket_type_id: str, slot_id: str):
    """重新查时段，避免用过期快照做判断。"""
    _, body = call("GET", f"/ticket/slots/{ticket_type_id}")
    items = (body or {}).get("data", {}).get("items", [])
    return next((item for item in items if item["id"] == slot_id), None)


def main() -> None:
    global TOKEN

    response = httpx.post(
        f"{BASE}/auth/token",
        data={"username": "admin", "password": "wenlv_admin_pass", "grant_type": "password"},
        timeout=60,
    )
    TOKEN = (response.json().get("data") or {}).get("access_token", "")
    print(f"[登录] HTTP {response.status_code} 角色 {(response.json().get('data') or {}).get('role')}")
    if not TOKEN:
        print("❌ 拿不到令牌，鉴权相关用例无法执行")
        return

    # 刻意挑选**有付费成人票**的景区：免费开放景区的成人票是 0 元，
    # 用它跑"金额 = 单价 × 数量""销售额"这类断言会变成恒真的空测试。
    status, body = call("GET", "/park?limit=50")
    parks = (body or {}).get("data", {}).get("items") or []
    if not parks:
        print("❌ 库中没有景区，请先运行 scripts/seed_parks.py 与 seed_tickets.py")
        return

    park, adult, types = None, None, []
    for candidate in parks:
        _, detail = call("GET", f"/ticket/park/{candidate['id']}")
        candidate_types = (detail or {}).get("data", {}).get("ticket_types") or []
        paid = next(
            (item for item in candidate_types if item["category"] == "adult" and item["price_cents"] > 0 and item["slots"]),
            None,
        )
        if paid is not None:
            park, adult, types = candidate, paid, candidate_types
            break
    if park is None or adult is None:
        print("❌ 没有找到「有付费成人票且有时段」的景区，请先运行 scripts/seed_tickets.py")
        return
    park_id = park["id"]
    slots = adult["slots"]
    oversell_slot, main_slot = slots[0], slots[1] if len(slots) > 1 else (slots[0], slots[0])
    print(f"[景区] {park.get('name')}  票种 {len(types)}  成人票 {adult['price']} 元")

    # ==================== 1. 鉴权 ====================
    print("\n[1] 鉴权（核销/退款属运营及以上）")
    status, _ = call("POST", "/ticket/checkin", json={"credential": "NOPE"})
    check("未带令牌核销返回 401", status == 401, f"HTTP {status}")

    # ==================== 2. 防超卖 ====================
    print("\n[2] 防超卖（把余票压到 3，再买 4）")
    base_sold = slot_of(adult["id"], oversell_slot["id"])["sold"]
    call("PUT", f"/ticket/admin/slots/{oversell_slot['id']}", auth=True, json={"inventory": base_sold + 3})
    snapshot = slot_of(adult["id"], oversell_slot["id"])
    check("造出余票恰为 3 的时段", snapshot["remaining"] == 3, f"已售 {base_sold} → 余票 {snapshot['remaining']}")

    status, body = call("POST", "/ticket/order", json={
        "park_id": park_id, "ticket_type_id": adult["id"], "slot_id": oversell_slot["id"],
        "quantity": 4, "visitor_ref": "verify",
    })
    detail = str((body or {}).get("detail"))
    check("超出余票被拒且原因是余票不足", status == 409 and "余票不足" in detail, detail)

    snapshot = slot_of(adult["id"], oversell_slot["id"])
    check("被拒的下单没有扣减库存", snapshot["sold"] == base_sold, f"sold={snapshot['sold']}")

    status, body = call("POST", "/ticket/order", json={
        "park_id": park_id, "ticket_type_id": adult["id"], "slot_id": oversell_slot["id"],
        "quantity": 3, "visitor_ref": "verify",
    })
    third = (body or {}).get("data") or {}
    check("正好买完余票（3 张）成功", status == 200 and third.get("quantity") == 3, f"订单 {third.get('order_no')}")
    check("成功下单后余票归零", slot_of(adult["id"], oversell_slot["id"])["remaining"] == 0)

    status, body = call("POST", "/ticket/order", json={
        "park_id": park_id, "ticket_type_id": adult["id"], "slot_id": oversell_slot["id"],
        "quantity": 1, "visitor_ref": "verify",
    })
    check("售罄后被拒", status == 409 and "余票不足" in str((body or {}).get("detail")))

    status, body = call("PUT", f"/ticket/admin/slots/{oversell_slot['id']}", auth=True, json={"inventory": base_sold})
    check("库存不能设到已售之下", status == 409, str((body or {}).get("detail")))

    if third.get("id"):
        status, body = call("POST", f"/ticket/order/{third['id']}/cancel")
        check("取消待支付订单成功", status == 200, (body or {}).get("data", {}).get("status_label", ""))
        restored = slot_of(adult["id"], oversell_slot["id"])
        check("取消后库存被释放", restored["sold"] == base_sold, f"{base_sold + 3} → {restored['sold']}")
    call("PUT", f"/ticket/admin/slots/{oversell_slot['id']}", auth=True, json={"inventory": 1000})

    # ==================== 3. 主链路 ====================
    print("\n[3] 下单 → 支付 → 二维码 → 核销")
    status, body = call("POST", "/ticket/order", json={
        "park_id": park_id, "ticket_type_id": adult["id"], "slot_id": main_slot["id"],
        "quantity": 2, "visitor_ref": "verify-visitor",
        "contact_name": "验证游客", "contact_phone": "13800001234",
    })
    order = (body or {}).get("data") or {}
    check("下单成功", status == 200 and bool(order.get("id")), f"订单号 {order.get('order_no')}")
    check("手机号输出即脱敏", order.get("contact_phone") == "138****34", str(order.get("contact_phone")))
    check("金额 = 单价 × 数量", order.get("amount_cents") == adult["price_cents"] * 2, f"{order.get('amount')} 元")

    status, body = call("POST", f"/ticket/order/{order['id']}/pay")
    paid = (body or {}).get("data") or {}
    tickets = paid.get("tickets") or []
    check("支付占位推进到已支付", paid.get("status") == "paid", str(paid.get("status_label")))
    check("一单一票：签发数量与购买数一致", len(tickets) == 2, f"{len(tickets)} 张")

    if tickets:
        response = httpx.get(f"{BASE}/ticket/qr/{tickets[0]['id']}", timeout=60)
        check(
            "二维码为合法 PNG",
            response.status_code == 200 and response.content[:8] == b"\x89PNG\r\n\x1a\n",
            f"{len(response.content)} 字节",
        )

    code_a = tickets[0]["code"] if tickets else ""
    code_b = tickets[1]["code"] if len(tickets) > 1 else ""
    status, body = call("POST", "/ticket/checkin", auth=True, json={"credential": code_a, "gate": "南门一号闸"})
    result = (body or {}).get("data") or {}
    check("首次核销成功", status == 200 and result.get("status") == "checked_in", str(result.get("gate")))
    check(
        "部分核销时订单不整体置为已核销",
        result.get("order_status") == "paid",
        str(result.get("order_status_label")),
    )

    status, body = call("POST", "/ticket/checkin", auth=True, json={"credential": code_a, "gate": "南门二号闸"})
    detail = str((body or {}).get("detail"))
    check(
        "重复入园被拒并说明上次时间与闸口",
        status == 409 and "重复入园" in detail and "南门一号闸" in detail,
        detail,
    )

    status, body = call("POST", "/ticket/checkin", auth=True, json={"credential": code_b, "gate": "南门一号闸"})
    result = (body or {}).get("data") or {}
    check("第二张票可独立核销", status == 200 and result.get("remaining_in_order") == 0)
    check("全部核销后订单转为已核销", result.get("order_status") == "checked_in")

    status, body = call("POST", f"/ticket/order/{order['id']}/refund", auth=True, json={"reason": "验证"})
    check("有票券已核销的订单不可退", status == 409, str((body or {}).get("detail")))

    # ==================== 4. 退款正路径 ====================
    print("\n[4] 退款正路径与库存释放")
    status, body = call("POST", "/ticket/order", json={
        "park_id": park_id, "ticket_type_id": adult["id"], "slot_id": main_slot["id"],
        "quantity": 1, "visitor_ref": "verify-refund",
    })
    ref_order = (body or {}).get("data") or {}
    call("POST", f"/ticket/order/{ref_order['id']}/pay")
    sold_before = slot_of(adult["id"], main_slot["id"])["sold"]
    status, body = call("POST", f"/ticket/order/{ref_order['id']}/refund", auth=True, json={"reason": "行程变更"})
    check("未核销订单可退款", status == 200, str((body or {}).get("data", {}).get("status_label")))
    sold_after = slot_of(adult["id"], main_slot["id"])["sold"]
    check("退款释放了库存", sold_after == sold_before - 1, f"{sold_before} → {sold_after}")
    check(
        "退款作废了电子票",
        all(item["status"] == "refunded" for item in ((body or {}).get("data", {}) or {}).get("tickets", [])),
    )

    # ==================== 5. 游客服务与评价 ====================
    print("\n[5] 游客服务（G4）")
    status, body = call("POST", "/service/request", json={
        "park_id": park_id, "visitor_ref": "verify-visitor",
        "category": "help", "content": "同行老人身体不适，需要轮椅协助", "contact": "13800001234",
    })
    urgent_ticket = (body or {}).get("data") or {}
    check("紧急求助提交成功", status == 200, str(urgent_ticket.get("category_label")))
    check("紧急求助自动置为加急", urgent_ticket.get("urgent") is True)

    call("POST", "/service/request", json={
        "park_id": park_id, "visitor_ref": "verify-visitor",
        "category": "consult", "content": "园内可以寄存行李吗？",
    })
    status, body = call("GET", f"/service/admin/requests?park_id={park_id}", auth=True)
    items = (body or {}).get("data", {}).get("items", [])
    check("加急求助排在普通咨询之前", bool(items) and items[0]["category"] == "help",
          str([(i["category_label"], i["urgent"]) for i in items[:3]]))

    status, body = call("POST", f"/service/admin/requests/{urgent_ticket['id']}/reply", auth=True,
                        json={"reply": "已联系服务台，轮椅 5 分钟内送达南门。", "handled_by": "admin"})
    check("回复后状态转为已回复", (body or {}).get("data", {}).get("status") == "resolved")

    _, body = call("GET", f"/review/park/{park_id}")
    baseline = ((body or {}).get("data") or {}).get("total", 0)
    call("POST", "/review", json={
        "park_id": park_id, "order_id": order["id"], "visitor_ref": "verify-visitor",
        "rating": 5, "content": "讲解很细致。", "tags": ["讲解好"],
    })
    _, body = call("GET", f"/review/park/{park_id}")
    after_first = ((body or {}).get("data") or {}).get("total", 0)
    check("新订单产生一条新评价", after_first == baseline + 1, f"{baseline} → {after_first}")
    call("POST", "/review", json={
        "park_id": park_id, "order_id": order["id"], "visitor_ref": "verify-visitor",
        "rating": 4, "content": "改一下评分。",
    })
    _, body = call("GET", f"/review/park/{park_id}")
    check("一单一评：重复提交是覆盖而非新增",
          ((body or {}).get("data") or {}).get("total") == after_first)

    print()
    print("=" * 62)
    if FAILURES:
        print(f"结论：{len(FAILURES)} 项失败")
        for item in FAILURES:
            print(f"   ✗ {item}")
    else:
        print("结论：全部通过 ✓")


if __name__ == "__main__":
    main()
