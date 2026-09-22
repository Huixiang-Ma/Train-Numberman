"""工单17 · 文字识别（主选 PaddleOCR / PP-OCRv4）

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成
技术栈：PaddleOCR（docs/01），用于碑刻、展板、指示牌识别。
"""
from __future__ import annotations

from typing import Any

from .base import OCRProvider


class PaddleOCRProvider(OCRProvider):
    name = "paddleocr"

    def __init__(self, lang: str = "ch", use_gpu: bool = False) -> None:
        from paddleocr import PaddleOCR

        self.lang = lang
        # PaddleOCR 3.x：关闭文档方向/去扭曲等非必要子模块，降低开销
        try:
            self._ocr = PaddleOCR(
                lang=lang,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                device="gpu" if use_gpu else "cpu",
            )
            self._api = "v3"
        except TypeError:
            self._ocr = PaddleOCR(use_angle_cls=True, lang=lang, use_gpu=use_gpu)
            self._api = "v2"

    @staticmethod
    def _extract_v3(result: Any) -> list[tuple[str, float]]:
        rows: list[tuple[str, float]] = []
        texts = None
        scores = None
        if isinstance(result, dict):
            texts = result.get("rec_texts")
            scores = result.get("rec_scores")
        else:
            texts = getattr(result, "rec_texts", None)
            scores = getattr(result, "rec_scores", None)
        if texts:
            for index, text in enumerate(texts):
                score = float(scores[index]) if scores is not None and index < len(scores) else 0.0
                rows.append((str(text), score))
        return rows

    def recognize(self, image: bytes) -> list[tuple[str, float]]:
        """识别文字；推理后端异常时返回空结果而不是抛错。

        PaddlePaddle 3.x 的 oneDNN 内核在部分 CPU 上不支持某些算子
        （NotImplementedError: ConvertPirAttribute2RuntimeAttribute not support），
        已在 core/config.py 里用 FLAGS_use_mkldnn=0 规避；这里再兜一层，
        避免 OCR 单点异常把整个 /perception/analyze 变成 500。
        """
        import io
        import logging

        import numpy as np
        from PIL import Image

        logger = logging.getLogger("wenlv.ocr")
        arr = np.array(Image.open(io.BytesIO(image)).convert("RGB"))

        try:
            if self._api == "v3":
                results = self._ocr.predict(input=arr)
                rows: list[tuple[str, float]] = []
                for item in results or []:
                    rows.extend(self._extract_v3(item))
                return rows

            raw = self._ocr.ocr(arr, cls=True)  # type: ignore[attr-defined]
            rows = []
            for page in raw or []:
                for line in page or []:
                    text, score = line[1][0], float(line[1][1])
                    rows.append((str(text), score))
            return rows
        except NotImplementedError as exc:
            logger.warning("PaddleOCR 推理后端不支持该算子（已尝试关闭 MKLDNN），本次 OCR 返回空：%s", str(exc)[:120])
            return []
        except Exception as exc:
            logger.warning("PaddleOCR 识别失败，本次 OCR 返回空：%s: %s", type(exc).__name__, exc)
            return []
