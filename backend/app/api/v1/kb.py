"""工单17 · 文旅知识库接口

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成
写入需运营及以上角色（RBAC）；文件批量解析入队由 Celery 异步执行。
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from ...providers.base import KbChunkData
from ...providers.registry import get_storage
from ...schemas import ApiResponse, IngestRequest
from ...services.kb import KBService
from ..deps import require_editor

router = APIRouter(prefix="/kb", tags=["kb"])


@router.post("/ingest", response_model=ApiResponse)
def ingest(payload: IngestRequest, _=Depends(require_editor)) -> ApiResponse:
    chunks: list[KbChunkData] = []
    for item in payload.chunks:
        chunks.append(
            KbChunkData(
                id=item.id or uuid.uuid4().hex,
                title=item.title,
                content=item.content,
                modality=item.modality,
                media_uri=item.media_uri,
                tags=list(item.tags),
                source=item.source or payload.source,
                authority=item.authority,
            )
        )
    result = KBService().ingest(chunks, document_title=payload.document_title, source=payload.source)
    return ApiResponse(data=result, trace_id=uuid.uuid4().hex)


@router.post("/ingest/file", response_model=ApiResponse)
async def ingest_file(
    file: UploadFile = File(...),
    title: str = Form(""),
    tags: str = Form(""),
    source: str = Form(""),
    _=Depends(require_editor),
) -> ApiResponse:
    """上传文档 → MinIO 存档 → 交由 Celery 解析分块入库。"""
    raw = await file.read()
    key = f"kb/{uuid.uuid4().hex}-{file.filename}"
    uri = get_storage().put_object(key, raw, content_type=file.content_type or "application/octet-stream")

    from ...tasks.ingest import ingest_document

    task = ingest_document.delay(
        uri=uri,
        filename=file.filename or "untitled",
        title=title or (file.filename or "未命名文档"),
        tags=[t for t in tags.split(",") if t],
        source=source,
    )
    return ApiResponse(data={"task_id": task.id, "uri": uri, "filename": file.filename}, trace_id=uuid.uuid4().hex)


@router.get("", response_model=ApiResponse)
def list_chunks(limit: int = 20, offset: int = 0, _=Depends(require_editor)) -> ApiResponse:
    items, total = KBService().list(limit=limit, offset=offset)
    return ApiResponse(data={"items": items, "total": total, "limit": limit, "offset": offset}, trace_id=uuid.uuid4().hex)


@router.get("/{chunk_id}", response_model=ApiResponse)
def get_chunk(chunk_id: str) -> ApiResponse:
    item = KBService().get(chunk_id)
    if item is None:
        raise HTTPException(status_code=404, detail="知识条目不存在")
    return ApiResponse(data=item, trace_id=uuid.uuid4().hex)


@router.put("/{chunk_id}", response_model=ApiResponse)
def update_chunk(chunk_id: str, patch: dict, _=Depends(require_editor)) -> ApiResponse:
    item = KBService().update(chunk_id, patch)
    if item is None:
        raise HTTPException(status_code=404, detail="知识条目不存在")
    return ApiResponse(data=item, trace_id=uuid.uuid4().hex)


@router.delete("/{chunk_id}", response_model=ApiResponse)
def delete_chunk(chunk_id: str, _=Depends(require_editor)) -> ApiResponse:
    ok = KBService().delete(chunk_id)
    if not ok:
        raise HTTPException(status_code=404, detail="知识条目不存在")
    return ApiResponse(data={"deleted": chunk_id}, trace_id=uuid.uuid4().hex)
