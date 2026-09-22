"""工单17 · 检索增强问答接口（LangGraph 编排）

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成
  POST /query             文本问答
  POST /query/multimodal   多模态问答（文本 + 图片 + 语音）
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ...core.config import get_settings
from ...providers.registry import get_asr
from ...schemas import ApiResponse, Citation
from ...services.graph import run_rag

router = APIRouter(tags=["query"])


def _citations(hits, limit: int = 3) -> list[dict]:
    rows = []
    for hit in hits[:limit]:
        chunk = hit.chunk
        rows.append(
            Citation(
                kb_id=chunk.id,
                title=chunk.title,
                source=chunk.source,
                score=round(float(hit.score), 4),
                rerank_score=round(float(hit.rerank_score), 4) if hit.rerank_score is not None else None,
            ).model_dump()
        )
    return rows


def _medias(hits) -> list[dict]:
    return [{"type": h.chunk.modality, "url": h.chunk.media_uri} for h in hits if h.chunk.media_uri]


@router.post("/query", response_model=ApiResponse)
def query(payload: dict) -> ApiResponse:
    from ...schemas import QueryRequest

    request = QueryRequest(**payload)
    settings = get_settings()
    state = run_rag(
        query=request.query,
        top_k=request.top_k or settings.top_k,
        rerank_top_n=request.rerank_top_n or settings.rerank_top_n,
        tags=request.tags,
        lang=request.lang,
    )
    hits = state.get("hits") or []
    data = {
        "answer_text": state.get("answer", ""),
        "citations": _citations(hits),
        "medias": _medias(hits),
        "ocr_text": state.get("ocr_text") or None,
        "lang": request.lang,
        "workflow": "langgraph:retrieve→rerank→generate",
    }
    return ApiResponse(data=data, trace_id=uuid.uuid4().hex)


@router.post("/query/multimodal", response_model=ApiResponse)
async def query_multimodal(
    query_text: str | None = Form(None, alias="query"),
    lang: str = Form("zh"),
    top_k: int = Form(0),
    rerank_top_n: int = Form(0),
    tags: str = Form(""),
    image: UploadFile | None = File(None),
    audio: UploadFile | None = File(None),
) -> ApiResponse:
    settings = get_settings()

    asr_text = ""
    if audio is not None:
        asr_text = get_asr().transcribe(await audio.read(), mime=audio.content_type or "audio/wav")

    question = " ".join(x for x in [query_text, asr_text] if x).strip()
    image_bytes = await image.read() if image is not None else None
    if image_bytes:
        from ...services.retrieval import RetrievalService

        try:
            RetrievalService.validate_image(image_bytes)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    state = run_rag(
        query=question,
        image=image_bytes,
        target="text",
        top_k=top_k or settings.top_k,
        rerank_top_n=rerank_top_n or settings.rerank_top_n,
        tags=[t for t in tags.split(",") if t] or None,
        lang=lang,
    )
    hits = state.get("hits") or []
    data = {
        "answer_text": state.get("answer", ""),
        "citations": _citations(hits),
        "medias": _medias(hits),
        "ocr_text": state.get("ocr_text") or None,
        "asr_text": asr_text or None,
        "lang": lang,
        "workflow": "langgraph:retrieve→rerank→generate",
    }
    return ApiResponse(data=data, trace_id=uuid.uuid4().hex)
