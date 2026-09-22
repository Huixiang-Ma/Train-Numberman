"""工单17 · 图文向量化（主选 Chinese-CLIP）

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成
技术栈：Chinese-CLIP（docs/01）。文本与图像共享向量空间，支撑以图搜文 / 以文搜图 / 以图搜图。

实现说明：直接取 CLS 向量（text/vision 塔）后经 projection 投影，再 L2 归一化。
不使用 `get_text_features`，因为该模型在部分 transformers 版本下 text 塔未启用 pooler，
会返回 None 导致 projection 报错；此处与官方 Chinese-CLIP 的取特征方式一致。
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Sequence

from .base import ClipProvider


class ChineseClipEmbedding(ClipProvider):
    name = "chinese-clip"

    def __init__(self, model_dir: str) -> None:
        if not Path(model_dir).exists():
            raise RuntimeError(f"未找到 Chinese-CLIP 权重目录：{model_dir}（请先执行 download_models.py clip）")
        import torch
        from transformers import ChineseCLIPModel, ChineseCLIPProcessor

        self.model_dir = str(model_dir)
        self._torch = torch
        self._model = ChineseCLIPModel.from_pretrained(self.model_dir)
        self._processor = ChineseCLIPProcessor.from_pretrained(self.model_dir)
        self._model.eval()
        self.dim = int(self._model.config.projection_dim)

    # ---------------- 内部：特征投影 ----------------
    def _project_text(self, inputs):
        torch = self._torch
        kwargs = {"input_ids": inputs.get("input_ids")}
        if inputs.get("attention_mask") is not None:
            kwargs["attention_mask"] = inputs.get("attention_mask")
        if inputs.get("token_type_ids") is not None:
            kwargs["token_type_ids"] = inputs.get("token_type_ids")

        outputs = self._model.text_model(**kwargs)
        pooled = getattr(outputs, "pooler_output", None)
        if pooled is None:
            pooled = outputs.last_hidden_state[:, 0, :]
        features = self._model.text_projection(pooled)
        return features / features.norm(dim=-1, keepdim=True)

    def _project_image(self, inputs):
        outputs = self._model.vision_model(pixel_values=inputs["pixel_values"])
        pooled = getattr(outputs, "pooler_output", None)
        if pooled is None:
            pooled = outputs.last_hidden_state[:, 0, :]
        features = self._model.visual_projection(pooled)
        return features / features.norm(dim=-1, keepdim=True)

    # ---------------- 对外 ----------------
    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        with self._torch.no_grad():
            inputs = self._processor(text=list(texts), return_tensors="pt", padding=True, truncation=True)
            features = self._project_text(inputs)
        return [[float(x) for x in row] for row in features.tolist()]

    def embed_images(self, images: Sequence[bytes]) -> list[list[float]]:
        if not images:
            return []
        from PIL import Image

        pil_images = [Image.open(io.BytesIO(raw)).convert("RGB") for raw in images]
        with self._torch.no_grad():
            inputs = self._processor(images=pil_images, return_tensors="pt")
            features = self._project_image(inputs)
        return [[float(x) for x in row] for row in features.tolist()]
