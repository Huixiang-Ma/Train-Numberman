"""工单17 · 文档解析入库异步任务

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成
技术栈：Celery（异步）+ unstructured（文档解析，docs/01）+ MinIO（取材）+ Milvus（向量）
"""
from __future__ import annotations

import logging
import tempfile
import uuid
from pathlib import Path

from ..providers.base import KbChunkData
from ..providers.registry import get_storage
from .celery_app import celery_app

logger = logging.getLogger("wenlv.tasks.ingest")

CHUNK_SIZE = 400
CHUNK_OVERLAP = 60


def extract_text(data: bytes, filename: str) -> str:
    """使用 unstructured 解析文档（技术栈主选）。"""
    from unstructured.partition.auto import partition

    suffix = Path(filename).suffix or ".txt"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        path = Path(tmp.name)
    try:
        elements = partition(filename=str(path))
        return "\n".join(str(element) for element in elements if str(element).strip())
    finally:
        path.unlink(missing_ok=True)


def split_chunks(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    clean = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if not clean:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(clean):
        end = min(start + size, len(clean))
        chunks.append(clean[start:end])
        if end >= len(clean):
            break
        start = end - overlap
    return chunks


@celery_app.task(name="kb.ingest_document")
def ingest_document(uri: str, filename: str, title: str = "", tags: list[str] | None = None, source: str = "") -> dict:
    from ..services.kb import KBService

    key = uri.split("/", 3)[-1] if uri.startswith("minio://") else uri
    data = get_storage().get_object(key)
    text = extract_text(data, filename)
    pieces = split_chunks(text)

    chunks = [
        KbChunkData(
            id=uuid.uuid4().hex,
            title=f"{title} #{index + 1}",
            content=piece,
            modality="text",
            tags=list(tags or []),
            source=source or filename,
        )
        for index, piece in enumerate(pieces)
    ]
    result = KBService().ingest(chunks, document_title=title or filename, source=source or filename)
    logger.info("文档入库完成：%s → %s", filename, result)
    return {"filename": filename, "chunks": len(chunks), **result}
