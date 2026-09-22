"""工单17 · 语音合成（主选 CosyVoice）

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成
技术栈：CosyVoice（docs/01）。CosyVoice 按官方仓库独立部署为推理服务，
本模块作为客户端调用其 HTTP 接口（默认 http://127.0.0.1:9880）。
"""
from __future__ import annotations

import base64
from typing import Any

import httpx

from .base import TTSProvider


class CosyVoiceTTS(TTSProvider):
    name = "cosyvoice"

    def __init__(self, endpoint: str = "http://127.0.0.1:9880", timeout: float = 60.0) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout

    def synthesize(self, text: str, lang: str = "zh", voice: str = "default") -> dict[str, Any]:
        payload = {"text": text, "language": lang, "voice": voice, "stream": False}
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(f"{self.endpoint}/tts", json=payload)
            resp.raise_for_status()
            body = resp.json()

        audio_b64 = body.get("audio_base64") or body.get("audio")
        if not audio_b64:
            raise RuntimeError("CosyVoice 服务未返回音频数据")
        audio_bytes = base64.b64decode(audio_b64)
        return {
            "format": body.get("format", "wav"),
            "size_bytes": len(audio_bytes),
            "sample_rate": body.get("sample_rate", 22050),
            "audio_base64": audio_b64,
            "note": "由 CosyVoice 推理服务合成（docs/01）",
        }
