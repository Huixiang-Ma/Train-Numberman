"""工单17 · 语音识别（主选 FunASR）

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成
技术栈：FunASR / Paraformer-zh（docs/01），权重经 ModelScope 拉取。
"""
from __future__ import annotations

import tempfile
import threading
from pathlib import Path

from .base import ASRProvider


class FunASRProvider(ASRProvider):
    name = "funasr"

    def __init__(self, model: str = "paraformer-zh") -> None:
        self.model_name = model
        self._lock = threading.Lock()
        self._model = None

    def _ensure(self) -> None:
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            from funasr import AutoModel

            self._model = AutoModel(model=self.model_name, disable_update=True)

    def transcribe(self, audio: bytes, mime: str = "audio/wav") -> str:
        self._ensure()
        suffix = ".wav" if "wav" in mime else ".mp3"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio)
            path = Path(tmp.name)
        try:
            result = self._model.generate(input=str(path))  # type: ignore[union-attr]
        finally:
            path.unlink(missing_ok=True)
        return "".join(str(item.get("text", "")) for item in result or [])
