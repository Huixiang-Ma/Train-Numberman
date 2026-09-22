"""工单17 · 重排序（主选 bge-reranker-v2）

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成
技术栈：bge-reranker-v2（docs/01）。提升 Top-K 精度，位于向量召回之后。
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .base import RerankerProvider


class BGEReranker(RerankerProvider):
    name = "bge-reranker-v2"

    def __init__(self, model_path: str) -> None:
        from sentence_transformers import CrossEncoder

        # 允许本地目录或 HuggingFace/镜像仓库 ID
        target = str(model_path)
        if not Path(target).exists() and "/" not in target:
            raise RuntimeError(f"未找到重排模型：{model_path}")
        self.model_path = target
        self._model = CrossEncoder(target, max_length=512, device="cpu")

    def rerank(self, query: str, candidates: Sequence[str], top_n: int) -> list[tuple[int, float]]:
        if not candidates:
            return []
        pairs = [(query, text) for text in candidates]
        scores = self._model.predict(pairs)
        ranked = sorted(range(len(candidates)), key=lambda i: float(scores[i]), reverse=True)
        return [(i, float(scores[i])) for i in ranked[:top_n]]
