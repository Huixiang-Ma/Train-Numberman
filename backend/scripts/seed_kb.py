"""工单17 · 灌入示例文旅知识库（PostgreSQL + Milvus）

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成
用法：python scripts/seed_kb.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db.base import create_all  # noqa: E402
from app.providers.base import KbChunkData  # noqa: E402
from app.services.kb import KBService  # noqa: E402

SEED = ROOT / "app" / "data" / "kb_seed.json"


def main() -> None:
    create_all()
    items = json.loads(SEED.read_text(encoding="utf-8"))
    chunks = [
        KbChunkData(
            id=item["id"],
            title=item["title"],
            content=item["content"],
            modality=item.get("modality", "text"),
            media_uri=item.get("media_uri"),
            tags=list(item.get("tags") or []),
            source=item.get("source", ""),
            authority=item.get("authority", ""),
        )
        for item in items
    ]
    service = KBService()
    result = service.ingest(chunks, document_title="示例文旅知识库", source="示例数据")
    print(f"灌入结果：{result}；知识条目总数：{service.count()}")


if __name__ == "__main__":
    main()
