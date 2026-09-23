"""工单17 · 检索增强问答接口（LangGraph 编排）

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成
  POST /query             文本问答
  POST /query/multimodal   多模态问答（文本 + 图片 + 语音）
"""
from __future__ import annotations

import logging
import time
import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ...core.config import get_settings
from ...providers.registry import get_asr
from ...schemas import ApiResponse, Citation
from ...services.analytics import record_query
from ...services.graph import run_rag

logger = logging.getLogger(__name__)

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
    started = time.perf_counter()
    state = run_rag(
        query=request.query,
        top_k=request.top_k or settings.top_k,
        rerank_top_n=request.rerank_top_n or settings.rerank_top_n,
        tags=request.tags,
        lang=request.lang,
    )
    hits = state.get("hits") or []
    # 埋点：让「游客需求洞察」有真实数据源（docs/09 G5）。写失败不影响本次问答。
    record_query(
        source="query",
        question=request.query,
        lang=request.lang,
        citations=len(hits),
        latency_ms=int((time.perf_counter() - started) * 1000),
    )
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
    asr_degraded = ""
    if audio is not None:
        try:
            asr_text = get_asr().transcribe(await audio.read(), mime=audio.content_type or "audio/wav")
        except Exception as exc:
            # 与 /dialog/multimodal 同一套降级约定：上游 ASR 不可用（额度/网络/故障）
            # 不能让整个多模态问答失败 —— 图片检索与文本问答部分仍然是有用的。
            logger.warning("语音转写失败，降级为纯文本问答：%s", exc)
            asr_degraded = "语音识别服务暂时不可用，本次已按文字问答处理"

    question = " ".join(x for x in [query_text, asr_text] if x).strip()
    image_bytes = await image.read() if image is not None else None
    if image_bytes:
        from ...services.retrieval import RetrievalService

        try:
            RetrievalService.validate_image(image_bytes)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    started = time.perf_counter()
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
    record_query(
        source="query",
        question=question,
        lang=lang,
        citations=len(hits),
        has_image=image_bytes is not None,
        has_audio=bool(asr_text),
        latency_ms=int((time.perf_counter() - started) * 1000),
    )
    data = {
        "answer_text": state.get("answer", ""),
        "citations": _citations(hits),
        "medias": _medias(hits),
        "ocr_text": state.get("ocr_text") or None,
        "asr_text": asr_text or None,
        "asr_degraded": asr_degraded or None,
        "lang": lang,
        "workflow": "langgraph:retrieve→rerank→generate",
    }
    return ApiResponse(data=data, trace_id=uuid.uuid4().hex)
