"""工单17 · 多模态检索接口

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成
  POST /search/text          以文搜文
  POST /search/text-to-image 以文搜图
  POST /search/image-to-text 以图搜文
  POST /search/image-to-image 以图搜图
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ...core.config import get_settings
from ...providers.base import Hit
from ...schemas import ApiResponse, SearchData, TextSearchRequest
from ...services.retrieval import RetrievalService

router = APIRouter(prefix="/search", tags=["search"])


def _hit_payload(hit: Hit) -> dict:
    chunk = hit.chunk
    return {
        "kb_id": chunk.id,
        "title": chunk.title,
        "content": chunk.content,
        "modality": chunk.modality,
        "media_uri": chunk.media_uri,
        "tags": list(chunk.tags),
        "source": chunk.source,
        "score": round(float(hit.score), 4),
        "rerank_score": round(float(hit.rerank_score), 4) if hit.rerank_score is not None else None,
    }


def _search_data(mode: str, hits: list[Hit], ocr_text: str | None = None, ocr_blocks: list | None = None) -> dict:
    return SearchData(
        mode=mode,
        hits=[_hit_payload(h) for h in hits],
        ocr_text=ocr_text,
        ocr_blocks=ocr_blocks,
    ).model_dump()


@router.post("/text", response_model=ApiResponse)
def search_text(payload: TextSearchRequest) -> ApiResponse:
    settings = get_settings()
    hits = RetrievalService().text_to_text(payload.query, top_k=payload.top_k or settings.top_k, tags=payload.tags)
    return ApiResponse(data=_search_data("text-to-text", hits), trace_id=uuid.uuid4().hex)


@router.post("/text-to-image", response_model=ApiResponse)
def search_text_to_image(payload: TextSearchRequest) -> ApiResponse:
    settings = get_settings()
    hits = RetrievalService().text_to_image(payload.query, top_k=payload.top_k or settings.top_k, tags=payload.tags)
    return ApiResponse(data=_search_data("text-to-image", hits), trace_id=uuid.uuid4().hex)


@router.post("/image-to-text", response_model=ApiResponse)
async def search_image_to_text(
    image: UploadFile = File(...),
    top_k: int = Form(0),
    tags: str = Form(""),
) -> ApiResponse:
    settings = get_settings()
    try:
        result = RetrievalService().image_search(
            await image.read(),
            top_k=top_k or settings.top_k,
            target="text",
            tags=[t for t in tags.split(",") if t] or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ApiResponse(
        data=_search_data("image-to-text", result["hits"], result["ocr_text"], result["ocr_blocks"]),
        trace_id=uuid.uuid4().hex,
    )


@router.post("/image-to-image", response_model=ApiResponse)
async def search_image_to_image(
    image: UploadFile = File(...),
    top_k: int = Form(0),
    tags: str = Form(""),
) -> ApiResponse:
    settings = get_settings()
    try:
        result = RetrievalService().image_search(
            await image.read(),
            top_k=top_k or settings.top_k,
            target="image",
            tags=[t for t in tags.split(",") if t] or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ApiResponse(
        data=_search_data("image-to-image", result["hits"], result["ocr_text"], result["ocr_blocks"]),
        trace_id=uuid.uuid4().hex,
    )
