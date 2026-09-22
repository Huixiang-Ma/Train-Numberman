"""工单17 · 能力装配

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成
按 docs/01-技术栈选型总表装配主选实现，不提供替代实现。

向量空间说明（跨模态检索的正确做法）：
  {collection}_text       → BGE-M3 文本空间（1024 维），用于以文搜文（语义检索）
  {collection}_clip_text  → Chinese-CLIP 文本空间（512 维），与图像向量同空间，用于以图搜文
  {collection}_image      → Chinese-CLIP 图像空间（512 维），用于以文搜图 / 以图搜图
"""
from __future__ import annotations

from functools import lru_cache

from ..core.config import get_settings
from .asr import FunASRProvider
from .base import ASRProvider, ClipProvider, DiagramRenderer, EmbeddingProvider, ImageProvider, LLMProvider, ObjectStorage, OCRProvider, RerankerProvider, TTSProvider, VectorStore, VideoComposer
from .clip import ChineseClipEmbedding
from .diagram import MermaidDiagramRenderer
from .embedding import BGEM3Embedding
from .llm import QwenLLM
from .map import SiteMapRenderer
from .ocr import PaddleOCRProvider
from .reranker import BGEReranker
from .siliconflow import SiliconFlowASR, SiliconFlowEmbedding, SiliconFlowImage, SiliconFlowLLM, SiliconFlowReranker, SiliconFlowTTS
from .storage import MinIOStorage
from .tts import CosyVoiceTTS
from .vector_milvus import MilvusVectorStore
from .video import FFmpegVideoComposer
from .vision_tasks import (
    ExpressionRecognizer,
    GestureRecognizer,
    ImageClassifier,
    MediaPipeExpressionRecognizer,
    MediaPipeGestureRecognizer,
    ObjectDetector,
    Segmenter,
    UltralyticsClassifier,
    UltralyticsDetector,
    UltralyticsSamSegmenter,
)


@lru_cache
def get_embedding() -> EmbeddingProvider:
    """BGE-M3：默认走 SiliconFlow API，避免本地驻留大模型。"""
    settings = get_settings()
    if settings.embedding_mode == "cloud":
        return SiliconFlowEmbedding(
            api_key=settings.siliconflow_api_key,
            base_url=settings.siliconflow_base_url,
            model=settings.sf_embedding_model,
            dim=settings.sf_embedding_dim,
        )
    return BGEM3Embedding(settings.bge_m3_dir)


@lru_cache
def get_clip() -> ClipProvider:
    """Chinese-CLIP：保留本地权重（云端无同名模型）。"""
    settings = get_settings()
    return ChineseClipEmbedding(settings.clip_dir)


@lru_cache
def get_text_store() -> VectorStore:
    settings = get_settings()
    return MilvusVectorStore(
        uri=settings.milvus_uri,
        collection=f"{settings.milvus_collection}_text",
        dim=get_embedding().dim,
        metric=settings.milvus_metric,
        index_type=settings.milvus_index_type,
        hnsw_m=settings.milvus_hnsw_m,
        hnsw_ef_construction=settings.milvus_hnsw_ef_construction,
        search_ef=settings.milvus_search_ef,
    )


@lru_cache
def get_clip_text_store() -> VectorStore:
    """Chinese-CLIP 文本空间：与图像向量同维度，用于「以图搜文」。"""
    settings = get_settings()
    return MilvusVectorStore(
        uri=settings.milvus_uri,
        collection=f"{settings.milvus_collection}_clip_text",
        dim=get_clip().dim,
        metric=settings.milvus_metric,
        index_type=settings.milvus_index_type,
        hnsw_m=settings.milvus_hnsw_m,
        hnsw_ef_construction=settings.milvus_hnsw_ef_construction,
        search_ef=settings.milvus_search_ef,
    )


@lru_cache
def get_image_store() -> VectorStore:
    settings = get_settings()
    return MilvusVectorStore(
        uri=settings.milvus_uri,
        collection=f"{settings.milvus_collection}_image",
        dim=get_clip().dim,
        metric=settings.milvus_metric,
        index_type=settings.milvus_index_type,
        hnsw_m=settings.milvus_hnsw_m,
        hnsw_ef_construction=settings.milvus_hnsw_ef_construction,
        search_ef=settings.milvus_search_ef,
    )


@lru_cache
def get_reranker() -> RerankerProvider:
    settings = get_settings()
    if settings.reranker_mode == "cloud":
        return SiliconFlowReranker(
            api_key=settings.siliconflow_api_key,
            base_url=settings.siliconflow_base_url,
            model=settings.sf_reranker_model,
        )
    return BGEReranker(settings.reranker)


@lru_cache
def get_llm() -> LLMProvider:
    settings = get_settings()
    if settings.llm_mode == "cloud":
        return SiliconFlowLLM(
            api_key=settings.siliconflow_api_key,
            base_url=settings.siliconflow_base_url,
            model=settings.sf_llm_model,
        )
    return QwenLLM(
        serving=settings.qwen_serving,
        model_path=settings.qwen_dir,
        base_url=settings.qwen_base_url,
        api_key=settings.qwen_api_key,
        model=settings.qwen_model,
        max_new_tokens=settings.qwen_max_new_tokens,
    )


@lru_cache
def get_ocr() -> OCRProvider:
    settings = get_settings()
    return PaddleOCRProvider(lang=settings.paddleocr_lang, use_gpu=settings.paddleocr_use_gpu)


@lru_cache
def get_asr() -> ASRProvider:
    settings = get_settings()
    if settings.asr_mode == "cloud":
        return SiliconFlowASR(
            api_key=settings.siliconflow_api_key,
            base_url=settings.siliconflow_base_url,
            model=settings.sf_asr_model,
        )
    return FunASRProvider(model=settings.funasr_model)


@lru_cache
def get_tts() -> TTSProvider:
    settings = get_settings()
    if settings.tts_mode == "cloud":
        return SiliconFlowTTS(
            api_key=settings.siliconflow_api_key,
            base_url=settings.siliconflow_base_url,
            model=settings.sf_tts_model,
            voice=settings.sf_tts_voice,
        )
    return CosyVoiceTTS(endpoint=settings.cosyvoice_endpoint)


@lru_cache
def get_storage() -> ObjectStorage:
    settings = get_settings()
    return MinIOStorage(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        bucket=settings.minio_bucket,
        secure=settings.minio_secure,
    )


# ==========================================================================
# 阶段三（工单18）· CV 深度图像任务与实时感知
# YOLO11（分类 / 检测跟踪）/ SAM 2（分割）/ MediaPipe（手势 / 表情）
# ==========================================================================
@lru_cache
def get_classifier() -> ImageClassifier:
    settings = get_settings()
    return UltralyticsClassifier(settings.cls_weights)


@lru_cache
def get_detector() -> ObjectDetector:
    settings = get_settings()
    return UltralyticsDetector(settings.det_weights, conf=settings.detect_conf)


@lru_cache
def get_segmenter() -> Segmenter:
    settings = get_settings()
    return UltralyticsSamSegmenter(settings.sam_weights)


@lru_cache
def get_gesture() -> GestureRecognizer:
    settings = get_settings()
    return MediaPipeGestureRecognizer(settings.mediapipe_dir / "gesture_recognizer.task")


@lru_cache
def get_expression() -> ExpressionRecognizer:
    settings = get_settings()
    return MediaPipeExpressionRecognizer(settings.mediapipe_dir / "face_landmarker.task")


# ==========================================================================
# 阶段四（工单19）· AIGC 内容生成
# 图像生成/风格迁移（通义系 Qwen-Image）、视频合成（FFmpeg + OpenCV）、流程图（Mermaid）
# ==========================================================================
@lru_cache
def get_image() -> ImageProvider:
    """图像生成与风格迁移：走 SiliconFlow（与其余云端能力同一取用方式）。

    docs/01 §4.7 主选「通义万相 / Stable Diffusion」——本项目取通义系云端模型。
    本地 Stable Diffusion 需 GPU 推理，本机为 CPU 环境，故不设本地分支。
    """
    settings = get_settings()
    if settings.image_mode != "cloud":
        raise RuntimeError("图像生成本机无 GPU，仅支持 image_mode=cloud（通义系云端模型）")
    return SiliconFlowImage(
        api_key=settings.siliconflow_api_key,
        base_url=settings.siliconflow_base_url,
        model=settings.sf_image_model,
        edit_model=settings.sf_image_edit_model,
        steps=settings.sf_image_steps,
        guidance=settings.sf_image_guidance,
    )


@lru_cache
def get_video() -> VideoComposer:
    """视频合成：FFmpeg（运镜/转场/音轨） + OpenCV（帧抽取）。"""
    return FFmpegVideoComposer(ffmpeg_bin=get_settings().ffmpeg_bin)


@lru_cache
def get_diagram() -> DiagramRenderer:
    """流程图：Mermaid 源码 + Pillow 直绘位图。"""
    return MermaidDiagramRenderer()


@lru_cache
def get_map() -> SiteMapRenderer:
    """导览地图：按景点真实坐标（PostGIS）直绘可打印的地图（工单20 场景13）。"""
    return SiteMapRenderer()
