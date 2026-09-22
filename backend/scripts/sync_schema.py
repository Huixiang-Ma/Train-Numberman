"""工单20 · 轻量结构同步（幂等 DDL）

工单编号：人工智能CV-AIGC-20-文旅Agent任务工单-功能集成测试与部署

为什么需要它：
  `Base.metadata.create_all()` 只负责**建缺失的表**，不会修改已存在表的列定义。
  集成测试阶段就撞到过一次：CreationAsset.result_mime 原为 varchar(64)，
  而 OOXML 的 MIME 有 73 个字符，生成活动回顾 PPT 时插入直接失败
  （StringDataRightTruncation），产物落库丢失——文件在 MinIO 里，但拿不到 asset_id。

本项目未引入 Alembic（工时与规模不匹配），因此用这个脚本承载"create_all 覆盖不到"
的列级变更，全部语句幂等，可反复执行。生产环境建议替换为 Alembic 版本化迁移。

用法：python scripts/sync_schema.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.base import engine  # noqa: E402

SCHEMA = get_settings().db_schema

# 每条都是幂等的列定义同步；ALTER ... TYPE 对同类型重复执行无副作用
STATEMENTS = [
    # MIME 最大 73 字符（OOXML pptx），64 会截断报错
    f"ALTER TABLE {SCHEMA}.creation_asset ALTER COLUMN result_mime TYPE varchar(128)",
    f"ALTER TABLE {SCHEMA}.media_asset ALTER COLUMN mime TYPE varchar(128)",
    # 审计路径带查询串时可能超过 256
    f"ALTER TABLE {SCHEMA}.audit_log ALTER COLUMN path TYPE varchar(320)",
    # —— docs/09 通用化（G1）：给已有景点补「所属景区」列 ——
    # create_all 只建缺失的表，不会给已存在的 attraction 加列，故在此补。
    # 可空：历史景点先落地，再由 seed_parks.py 回填归属。
    f"ALTER TABLE {SCHEMA}.attraction ADD COLUMN IF NOT EXISTS park_id varchar(32)",
    f"CREATE INDEX IF NOT EXISTS ix_attraction_park_id ON {SCHEMA}.attraction (park_id)",
    # 外键需条件判断（ADD CONSTRAINT 不支持 IF NOT EXISTS），用 DO 块幂等
    (
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'attraction_park_id_fkey') THEN "
        f"ALTER TABLE {SCHEMA}.attraction ADD CONSTRAINT attraction_park_id_fkey "
        f"FOREIGN KEY (park_id) REFERENCES {SCHEMA}.park(id); "
        "END IF; END $$;"
    ),
]


def main() -> None:
    applied = 0
    skipped: list[str] = []
    # 每条语句单独提交：PostgreSQL 中一条 DDL 失败会中止整个事务块，
    # 后续语句会以 InFailedSqlTransaction 连带失败，因此必须逐条独立事务。
    for statement in STATEMENTS:
        try:
            with engine.begin() as conn:
                conn.execute(text(statement))
            applied += 1
        except Exception as exc:  # 表尚未创建时跳过（先执行一次应用启动即可建表）
            skipped.append(f"{statement[:70]} -> {type(exc).__name__}")

    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT table_name, column_name, character_maximum_length "
                "FROM information_schema.columns "
                "WHERE table_schema = :schema AND column_name IN ('mime', 'result_mime', 'path') "
                "ORDER BY table_name"
            ),
            {"schema": SCHEMA},
        ).all()
        # 通用化新增列的存在性单独确认（它没有 character_maximum_length 之外的语义要报）
        park_link = conn.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_schema = :schema AND table_name = 'attraction' AND column_name = 'park_id'"
            ),
            {"schema": SCHEMA},
        ).first()

    print(f"已执行 {applied}/{len(STATEMENTS)} 条结构同步语句")
    for item in skipped:
        print(f"  跳过：{item}")
    for table, column, length in rows:
        print(f"  {table}.{column} -> varchar({length})")
    if park_link is None:
        print("  ⚠️ attraction.park_id 仍不存在（attraction 表尚未创建？先启动一次应用）")
    else:
        print(f"  attraction.park_id 已就绪（is_nullable={park_link[0]}）")


if __name__ == "__main__":
    main()
