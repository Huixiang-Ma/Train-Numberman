"""工单17 · 多模态检索与重排序服务

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成
链路：BGE-M3 / Chinese-CLIP 向量化 → Milvus 召回 → bge-reranker-v2 重排序。
支持：以文搜文、以图搜文、以文搜图、以图搜图。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Sequence

from ..providers.base import Hit
from ..providers.registry import (
    get_clip,
    get_clip_text_store,
    get_embedding,
    get_image_store,
    get_ocr,
    get_reranker,
    get_text_store,
)

logger = logging.getLogger("wenlv.retrieval")


class RetrievalService:
    def __init__(self) -> None:
        self.embedding = get_embedding()
        self.clip = get_clip()
        self.text_store = get_text_store()        # BGE-M3 文本空间
        self.clip_text_store = get_clip_text_store()  # Chinese-CLIP 文本空间
        self.image_store = get_image_store()      # Chinese-CLIP 图像空间

    # ---------------- 重排序 ----------------
    @staticmethod
    def rerank(query: str, hits: Sequence[Hit], top_n: int) -> list[Hit]:
        """重排序；上游不可用时**降级为向量召回顺序**而不是抛错。

        工单20 集成测试暴露的问题：重排走云端额度，一旦额度/网络异常，
        `raise_for_status()` 会一路冒到接口层，使 /dialog 直接 500。
        对话是游客最核心的功能，绝不能因为一个"精排"组件不可用就整体失败——
        降级为按原始向量相似度取 Top-N，检索质量略降但链路仍然可用。
        """
        if not hits:
            return []
        candidates = [h.chunk.content for h in hits]
        try:
            ranked = get_reranker().rerank(query, candidates, min(top_n, len(candidates)))
        except Exception as exc:
            logger.warning("重排序不可用，降级为向量召回顺序：%s: %s", type(exc).__name__, exc)
            return list(hits[:top_n])
        output: list[Hit] = []
        for index, score in ranked:
            hit = hits[index]
            hit.rerank_score = score
            output.append(hit)
        return output

    # ---------------- 以文搜文 ----------------
    def text_to_text(
        self,
        query: str,
        top_k: int,
        tags: Sequence[str] | None = None,
    ) -> list[Hit]:
        """文本检索；向量化不可用时返回空结果（由上游决定如何提示游客）。

        返回空列表而不是抛错：检索为空是"没有资料"这一业务状态，
        生成层已有对应的友好提示语（见 GenerationService.generate）。
        """
        try:
            vector = self.embedding.embed_query(query)
        except Exception as exc:
            logger.warning("文本向量化不可用，本次检索返回空结果：%s: %s", type(exc).__name__, exc)
            return []
        try:
            hits = self.text_store.search(vector, top_k=top_k, tags=tags)
        except Exception as exc:
            logger.warning("向量检索不可用，本次检索返回空结果：%s: %s", type(exc).__name__, exc)
            return []
        return self.rerank(query, hits, top_k)

    # ---------------- 以文搜图 ----------------
    def text_to_image(
        self,
        query: str,
        top_k: int,
        tags: Sequence[str] | None = None,
    ) -> list[Hit]:
        """以文搜图；CLIP 或图像向量库不可用时返回空结果。

        这里补的是**同类漏改**：先前只给 text_to_text 与 rerank 加了兜底，
        CLIP 相关的路径仍是裸调用。CLIP 虽为本地权重，但加载失败或内存不足
        （本机 16GB，需与 PyTorch/Paddle 共存）同样会抛错并让 /dialog 500。
        """
        try:
            vector = self.clip.embed_texts([query])[0]
        except Exception as exc:
            logger.warning("图文向量化不可用，以文搜图返回空结果：%s: %s", type(exc).__name__, exc)
            return []
        try:
            hits = self.image_store.search(vector, top_k=top_k, tags=tags)
        except Exception as exc:
            logger.warning("图像向量检索不可用，返回空结果：%s: %s", type(exc).__name__, exc)
            return []
        return self.rerank(query, hits, top_k)

    # ---------------- 图片校验 ----------------
    @staticmethod
    def validate_image(raw: bytes) -> None:
        """校验上传内容是否为可用图片；不合法时抛出 ValueError。"""
        import io

        from PIL import Image

        try:
            with Image.open(io.BytesIO(raw)) as image:
                image.verify()
        except Exception as exc:
            raise ValueError("图片数据无法解析，请上传有效的图片文件（JPG/PNG/WEBP）") from exc

    # ---------------- 以图搜文 / 以图搜图 ----------------
    def image_search(
        self,
        image: bytes,
        top_k: int,
        target: str = "text",
        tags: Sequence[str] | None = None,
    ) -> dict:
        """以图搜文 / 以图搜图；图像侧不可用时返回空结果而不是抛错。

        注意 `validate_image` 的异常**故意不吞**：上传的不是图片属于游客输入错误，
        应当以 400 明确告知；而"模型不可用"是服务侧问题，应降级为空结果。
        """
        self.validate_image(image)
        try:
            vector = self.clip.embed_images([image])[0]
        except Exception as exc:
            logger.warning("图像向量化不可用，以图搜图返回空结果：%s: %s", type(exc).__name__, exc)
            return {"hits": [], "ocr_text": "", "ocr_blocks": []}

        # 以图搜文走 CLIP 文本空间（与图像向量同空间）；以图搜图走图像空间
        store = self.clip_text_store if target == "text" else self.image_store

        ocr_rows: list[tuple[str, float]] = []
        try:
            ocr_rows = get_ocr().recognize(image)
        except Exception:
            ocr_rows = []
        ocr_text = "\n".join(text for text, _ in ocr_rows)

        try:
            hits = store.search(vector, top_k=top_k, tags=tags)
        except Exception as exc:
            logger.warning("向量检索不可用，本次返回空结果：%s: %s", type(exc).__name__, exc)
            hits = []
        rerank_query = ocr_text or "图片内容讲解"
        hits = self.rerank(rerank_query, hits, top_k)

        return {
            "hits": hits,
            "ocr_text": ocr_text,
            "ocr_blocks": [{"text": text, "score": round(score, 3)} for text, score in ocr_rows],
        }

    # ---------------- 素材写入对象存储后入库 ----------------
    @staticmethod
    def guess_media_type(filename: str) -> str:
        suffix = Path(filename).suffix.lower()
        if suffix in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
            return "image"
        if suffix in {".mp4", ".mov", ".avi", ".mkv"}:
            return "video"
        if suffix in {".wav", ".mp3", ".m4a", ".flac"}:
            return "audio"
        return "text"
