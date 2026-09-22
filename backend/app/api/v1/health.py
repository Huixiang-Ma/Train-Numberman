"""工单17 · 健康与就绪检查

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成
readyz 实际探测各组件（PostgreSQL / Redis / Milvus / MinIO）；
为避免健康检查触发本地模型加载，此处不实例化向量化 / CLIP 等能力对象。
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter
from sqlalchemy import text

from ...core.config import get_settings
from ...db.base import engine
from ...providers.registry import get_storage
from ...schemas import ApiResponse

router = APIRouter(tags=["health"])


def _check_database() -> dict:
    try:
        with engine.connect() as conn:
            version = conn.execute(text("select postgis_version()")).scalar()
        return {"ok": True, "postgis": version}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _check_redis() -> dict:
    try:
        import redis

        client = redis.Redis.from_url(get_settings().redis_url)
        return {"ok": bool(client.ping())}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _check_milvus() -> dict:
    try:
        from pymilvus import MilvusClient

        settings = get_settings()
        client = MilvusClient(uri=settings.milvus_uri)
        collections = [c for c in client.list_collections() if c.startswith(settings.milvus_collection)]
        return {"ok": True, "collections": collections}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _check_minio() -> dict:
    try:
        return {"ok": True, "bucket": get_storage().bucket}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _declared_stack(settings) -> dict:
    return {
        "database": "PostgreSQL 16 + PostGIS",
        "cache": "Redis 7",
        "vector_store": "Milvus (HNSW)",
        "object_storage": "MinIO",
        "embedding": f"BGE-M3 ({settings.embedding_mode})",
        "clip": "Chinese-CLIP (local)",
        "reranker": f"bge-reranker-v2-m3 ({settings.reranker_mode})",
        "llm": f"Qwen ({settings.llm_mode})",
        "ocr": f"PaddleOCR ({settings.paddleocr_lang})",
        "asr": f"FunASR/SenseVoice ({settings.asr_mode})",
        "tts": f"CosyVoice ({settings.tts_mode})",
        "orchestration": "LangGraph",
        "model_api_base": settings.siliconflow_base_url,
    }


@router.get("/healthz", response_model=ApiResponse)
def healthz() -> ApiResponse:
    return ApiResponse(data={"status": "up"}, trace_id=uuid.uuid4().hex)


@router.get("/readyz", response_model=ApiResponse)
def readyz() -> ApiResponse:
    settings = get_settings()
    data = {
        "work_order": settings.work_order,
        "stack": _declared_stack(settings),
        "services": {
            "database": _check_database(),
            "redis": _check_redis(),
            "milvus": _check_milvus(),
            "minio": _check_minio(),
        },
    }
    return ApiResponse(data=data, trace_id=uuid.uuid4().hex)


@router.get("/stack", response_model=ApiResponse)
def stack() -> ApiResponse:
    """回显当前生效的技术栈与调用方式（云端 API / 本地权重），供验收核对。"""
    settings = get_settings()
    data = {
        "model_api_base": settings.siliconflow_base_url,
        "llm": settings.sf_llm_model if settings.llm_mode == "cloud" else str(settings.qwen_dir),
        "llm_mode": settings.llm_mode,
        "embedding_model": (
            settings.sf_embedding_model if settings.embedding_mode == "cloud" else str(settings.bge_m3_dir)
        ),
        "embedding_mode": settings.embedding_mode,
        "clip_model": str(settings.clip_dir),
        "clip_mode": settings.clip_mode,
        "reranker": settings.sf_reranker_model if settings.reranker_mode == "cloud" else settings.reranker,
        "reranker_mode": settings.reranker_mode,
        "asr": settings.sf_asr_model if settings.asr_mode == "cloud" else settings.funasr_model,
        "asr_mode": settings.asr_mode,
        "tts": settings.sf_tts_model if settings.tts_mode == "cloud" else settings.cosyvoice_endpoint,
        "tts_mode": settings.tts_mode,
        "milvus_uri": settings.milvus_uri,
        "milvus_collection": settings.milvus_collection,
        "minio_bucket": settings.minio_bucket,
    }
    return ApiResponse(data=data, trace_id=uuid.uuid4().hex)
