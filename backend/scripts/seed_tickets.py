"""docs/09 G3 · 票务种子数据（批次 5）

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成

**为什么由景区属性推导、而不是写一张"景区名 → 票价"的映射表**：
本项目是通用多景区平台，景区是运营配置出来的，不是代码里写死的。
按名字硬编码的话，运营新建一个景区就得到代码里加一行，否则票务页永远是空的 ——
那正好把"通用化"这件事做反了。因此这里只依赖 park 上已有的**等级、标签、承载量**
三个字段来推导票种与库存，任何新景区都能自动获得可用的票务配置。

幂等：按 (park_id, name) 判断票种是否已存在则跳过；时段按 (票种, 日期, 开始时间) 去重。
重复执行不会把库存翻倍 —— 那比"插入失败"更难发现。

用法：`python scripts/seed_tickets.py`（需先跑过 seed_parks.py）
"""
from __future__ import annotations

import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from app.db.base import SessionLocal, create_all  # noqa: E402
from app.db.models import Park, TicketSlot, TicketType  # noqa: E402

# 等级 → 成人基准票价（分）。取整到元，便于票面展示。
LEVEL_PRICE = {
    "5A": 10000,
    "4A": 4500,
    "3A": 3000,
    "2A": 2000,
    "1A": 1500,
}
DEFAULT_PRICE = 3000

# 免费开放景区的"讲解服务票"价格：园门免费，但深度讲解是真实在售的服务。
GUIDE_SERVICE_PRICE = 6000

SLOT_PLAN = [("08:00", "11:00"), ("11:00", "14:00"), ("14:00", "17:00")]
DAYS = 7


def _is_free(park: Park) -> bool:
    return "免费开放" in (park.tags or [])


def _adult_price(park: Park) -> int:
    if _is_free(park):
        return 0
    return LEVEL_PRICE.get((park.level or "").strip().upper(), DEFAULT_PRICE)


def _plan_types(park: Park) -> list[tuple[str, str, int, str, int]]:
    """推导该景区的票种：(名称, 类别, 单价分, 票务须知, 有效天数)"""
    price = _adult_price(park)
    label = park.level or "本景区"

    if price == 0:
        # 免费开放：园门不售票，但保留"预约名额"与"讲解服务"两个真实在售项
        return [
            ("免费预约票", "adult", 0, "园门免费开放。预约仅用于分时段限流，入园时不核销收费。", 1),
            ("深度讲解票", "combo", GUIDE_SERVICE_PRICE, "含持证讲解员两小时陪同，可与免费预约同时使用。", 1),
        ]

    types = [
        ("成人票", "adult", price, f"{label}景区全园通票，当日一次有效。", 1),
        ("学生票", "student", price // 2, "凭全日制本科及以下学生证入园，研究生不适用。", 1),
    ]
    # 4A 及以上才配老人优惠：低等级景区票价本身已低于优惠线，再打折没有意义
    if (park.level or "").strip().upper() in ("5A", "4A"):
        types.append(("老人票", "senior", price // 2, "60 周岁以上凭有效身份证件入园。", 1))
    # 世界遗产景区配联票：这类景区讲解与特展需求集中
    if "世界遗产" in (park.tags or []):
        types.append(("联票（含讲解）", "combo", int(price * 1.6), "含全园门票与一次深度讲解，有效期 2 天。", 2))
    return types


def main() -> None:
    create_all()

    created_types = 0
    created_slots = 0
    skipped = 0

    with SessionLocal() as db:
        parks = db.scalars(select(Park).order_by(Park.name)).all()
        if not parks:
            print("⚠️ 库中没有景区，请先运行 scripts/seed_parks.py")
            return

        for park in parks:
            plan = _plan_types(park)
            # 库存按景区日承载量拆分：承载量是景区级的事实，票种级再各自乘一份会超卖整个景区。
            capacity = int(park.daily_capacity or 0) or 3000
            per_slot = max(20, capacity // (len(plan) * len(SLOT_PLAN)))

            for name, category, price_cents, notice, valid_days in plan:
                existing = db.scalars(
                    select(TicketType).where(TicketType.park_id == park.id, TicketType.name == name)
                ).first()
                if existing is not None:
                    skipped += 1
                    continue

                ticket_type = TicketType(
                    id=uuid.uuid4().hex,
                    park_id=park.id,
                    name=name,
                    category=category,
                    price_cents=price_cents,
                    refundable=True,
                    valid_days=valid_days,
                    notice=notice,
                    status="on_sale",
                )
                db.add(ticket_type)
                db.flush()
                created_types += 1

                today = date.today()
                for offset in range(DAYS):
                    slot_date = today + timedelta(days=offset)
                    for start_time, end_time in SLOT_PLAN:
                        db.add(
                            TicketSlot(
                                id=uuid.uuid4().hex,
                                ticket_type_id=ticket_type.id,
                                slot_date=slot_date,
                                start_time=start_time,
                                end_time=end_time,
                                inventory=per_slot,
                                sold=0,
                            )
                        )
                        created_slots += 1

            free_mark = "免费开放" if _is_free(park) else f"成人 {_adult_price(park) / 100:.0f} 元"
            print(f"  {park.name:<12} {park.level or '--':<3} 日承载 {capacity:>6}  {free_mark:<12} "
                  f"票种 {len(plan)}  每时段库存 {per_slot}")
            db.commit()

        print()
        print(f"  票种：新建 {created_types}，跳过已存在 {skipped}")
        print(f"  时段：新建 {created_slots}（未来 {DAYS} 天 × {len(SLOT_PLAN)} 时段）")
        print(f"  库中共：票种 {len(db.scalars(select(TicketType)).all())}，"
              f"时段 {len(db.scalars(select(TicketSlot)).all())}")


if __name__ == "__main__":
    main()
