"""工单17 · 文本向量化（主选 BGE-M3）

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成
技术栈：BGE-M3（docs/01）。本地权重目录由 BGE_M3_PATH 指定，不提供替代实现。
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .base import EmbeddingProvider


class BGEM3Embedding(EmbeddingProvider):
    name = "bge-m3"

    def __init__(self, model_dir: Path) -> None:
        if not Path(model_dir).exists():
            raise RuntimeError(f"未找到 BGE-M3 权重目录：{model_dir}（请先执行 deploy/models/download_models.py bge）")
        from sentence_transformers import SentenceTransformer  # 延迟导入

        self.model_dir = str(model_dir)
        self._model = SentenceTransformer(self.model_dir, device="cpu")
        self.dim = int(self._model.get_sentence_embedding_dimension())

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._model.encode(
            list(texts),
            normalize_embeddings=True,
            batch_size=8,
            show_progress_bar=False,
        )
        return [[float(x) for x in v] for v in vectors]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]
