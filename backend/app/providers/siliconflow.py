"""工单17 · 硅基流动（SiliconFlow）API 接入

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成
说明：按最终确认，BGE-M3（向量化）、Qwen（生成）、FunASR/SenseVoice（语音识别）、
      bge-reranker-v2-m3（重排序）与 CosyVoice（语音合成）统一通过 SiliconFlow 的
      OpenAI 兼容 API 调用，不在本地驻留权重。

接口（Base URL 默认 https://api.siliconflow.cn/v1）：
  POST /embeddings              文本向量化（BAAI/bge-m3，1024 维）
  POST /rerank                  重排序（BAAI/bge-reranker-v2-m3）
  POST /chat/completions        对话生成（Qwen）
  POST /audio/transcriptions    语音识别（FunAudioLLM/SenseVoiceSmall）
  POST /audio/speech            语音合成（FunAudioLLM/CosyVoice2-0.5B）
"""
from __future__ import annotations

import base64
import logging
import random
import time
from typing import Any, Sequence

import httpx

from .base import ASRProvider, EmbeddingProvider, ImageProvider, LLMProvider, RerankerProvider, TTSProvider

EMBED_BATCH = 16

logger = logging.getLogger("wenlv.siliconflow")

# 可重试的瞬时网络故障：代理掐断 TLS、连接被重置、超时、协议错误等
RETRYABLE_ERRORS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    httpx.RemoteProtocolError,
    httpx.ReadError,
)
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _runtime_defaults() -> tuple[int, bool]:
    """从全局配置读取重试次数与代理策略；配置不可用时退回安全默认值。"""
    try:
        from ..core.config import get_settings

        settings = get_settings()
        return int(settings.siliconflow_max_retries), bool(settings.siliconflow_trust_env)
    except Exception:  # 配置加载失败不应阻断调用链
        return 3, False


class _SiliconFlowBase:
    """SiliconFlow API 基类。

    出网健壮性（见 deploy/logs 中出现的 [SSL: UNEXPECTED_EOF_WHILE_READING]）：
      1) 默认 trust_env=False —— 不读取 HTTP(S)_PROXY 环境变量，
         避免系统代理把到 api.siliconflow.cn 的 TLS 握手掐断；
      2) 瞬时网络故障按指数退避自动重试，单次抖动不再导致整个请求失败。
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        timeout: float = 60.0,
        max_retries: int | None = None,
        trust_env: bool | None = None,
    ) -> None:
        default_retries, default_trust_env = _runtime_defaults()
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max(0, default_retries if max_retries is None else max_retries)
        self.trust_env = default_trust_env if trust_env is None else trust_env

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise RuntimeError("未配置 SILICONFLOW_API_KEY，请在 backend/.env 中填写")
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=self.timeout, headers=self._headers(), trust_env=self.trust_env)

    def _post(
        self,
        path: str,
        *,
        json: Any = None,
        files: Any = None,
        data: Any = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        url = f"{self.base_url}{path}"
        attempt = 0
        while True:
            try:
                with httpx.Client(
                    timeout=timeout or self.timeout,
                    headers=headers or self._headers(),
                    trust_env=self.trust_env,
                ) as client:
                    response = client.post(url, json=json, files=files, data=data)
                    response.raise_for_status()
                    return response
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status not in RETRYABLE_STATUS or attempt >= self.max_retries:
                    raise
                logger.warning("SiliconFlow %s 返回 %d，将重试", path, status)
            except RETRYABLE_ERRORS as exc:
                if attempt >= self.max_retries:
                    raise
                logger.warning(
                    "SiliconFlow %s 第 %d 次失败（%s），将重试",
                    path,
                    attempt + 1,
                    type(exc).__name__,
                )
            # 指数退避 + 抖动，避免重试风暴
            delay = min(2.0, 0.35 * (2**attempt)) + random.uniform(0.0, 0.25)
            time.sleep(delay)
            attempt += 1


# --------------------------------------------------------------------------
# 文本向量化：BGE-M3
# --------------------------------------------------------------------------
class SiliconFlowEmbedding(_SiliconFlowBase, EmbeddingProvider):
    name = "siliconflow:bge-m3"

    def __init__(self, api_key: str, base_url: str, model: str = "BAAI/bge-m3", dim: int = 1024) -> None:
        _SiliconFlowBase.__init__(self, api_key, base_url, timeout=90.0)
        self.model = model
        self.dim = dim

    def _request(self, texts: Sequence[str]) -> list[list[float]]:
        resp = self._post(
            "/embeddings",
            json={"model": self.model, "input": list(texts), "encoding_format": "float"},
        )
        payload = resp.json()
        rows = sorted(payload["data"], key=lambda item: item.get("index", 0))
        return [[float(x) for x in row["embedding"]] for row in rows]

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors: list[list[float]] = []
        for start in range(0, len(texts), EMBED_BATCH):
            vectors.extend(self._request(texts[start : start + EMBED_BATCH]))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]


# --------------------------------------------------------------------------
# 重排序：bge-reranker-v2-m3
# --------------------------------------------------------------------------
class SiliconFlowReranker(_SiliconFlowBase, RerankerProvider):
    name = "siliconflow:bge-reranker-v2-m3"

    def __init__(self, api_key: str, base_url: str, model: str = "BAAI/bge-reranker-v2-m3") -> None:
        _SiliconFlowBase.__init__(self, api_key, base_url, timeout=90.0)
        self.model = model

    def rerank(self, query: str, candidates: Sequence[str], top_n: int) -> list[tuple[int, float]]:
        if not candidates:
            return []
        resp = self._post(
            "/rerank",
            json={
                "model": self.model,
                "query": query,
                "documents": [str(c) for c in candidates],
                "top_n": min(top_n, len(candidates)),
                "return_documents": False,
            },
        )
        payload = resp.json()
        results = payload.get("results") or []
        return [(int(item["index"]), float(item["relevance_score"])) for item in results]


# --------------------------------------------------------------------------
# 生成：Qwen
# --------------------------------------------------------------------------
class SiliconFlowLLM(_SiliconFlowBase, LLMProvider):
    name = "siliconflow:qwen"

    def __init__(self, api_key: str, base_url: str, model: str = "Qwen/Qwen2.5-7B-Instruct") -> None:
        _SiliconFlowBase.__init__(self, api_key, base_url, timeout=120.0)
        self.model = model

    def generate(self, prompt: str, system: str | None = None, max_new_tokens: int | None = None) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": max_new_tokens or 512,
        }
        resp = self._post("/chat/completions", json=body)
        payload = resp.json()
        return payload["choices"][0]["message"]["content"].strip()


# --------------------------------------------------------------------------
# 语音识别：FunASR / SenseVoice
# --------------------------------------------------------------------------
class SiliconFlowASR(_SiliconFlowBase, ASRProvider):
    name = "siliconflow:sensevoice"

    def __init__(self, api_key: str, base_url: str, model: str = "FunAudioLLM/SenseVoiceSmall") -> None:
        _SiliconFlowBase.__init__(self, api_key, base_url, timeout=180.0)
        self.model = model

    def transcribe(self, audio: bytes, mime: str = "audio/wav") -> str:
        suffix = ".wav" if "wav" in mime else ".mp3"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        files = {"file": (f"audio{suffix}", audio, mime)}
        resp = self._post("/audio/transcriptions", files=files, data={"model": self.model}, headers=headers)
        payload = resp.json()
        return str(payload.get("text", "")).strip()


# --------------------------------------------------------------------------
# 语音合成：CosyVoice
# --------------------------------------------------------------------------
class SiliconFlowTTS(_SiliconFlowBase, TTSProvider):
    name = "siliconflow:cosyvoice"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str = "FunAudioLLM/CosyVoice2-0.5B",
        voice: str = "FunAudioLLM/CosyVoice2-0.5B:anna",
    ) -> None:
        _SiliconFlowBase.__init__(self, api_key, base_url, timeout=120.0)
        self.model = model
        self.voice = voice

    def synthesize(self, text: str, lang: str = "zh", voice: str = "default") -> dict[str, Any]:
        body = {
            "model": self.model,
            "input": text,
            "voice": self.voice if voice == "default" else voice,
            "response_format": "mp3",
        }
        headers = self._headers()
        headers.pop("Content-Type", None)
        audio = self._post("/audio/speech", json=body, headers=headers).content
        return {
            "format": "mp3",
            "size_bytes": len(audio),
            "audio_base64": base64.b64encode(audio).decode("ascii"),
            "note": "由 SiliconFlow CosyVoice API 合成",
        }


# --------------------------------------------------------------------------
# 图像生成与风格迁移：Qwen-Image（工单19）
# --------------------------------------------------------------------------
class SiliconFlowImage(_SiliconFlowBase, ImageProvider):
    """图像生成 / 图生图，对应 docs/01 §4.7「图像生成」与「风格迁移」。

    接口：POST /images/generations（OpenAI 兼容风格）
      - 文生图：{"model": <image_model>, "prompt": ...}
      - 图生图：额外传 "image": "data:image/png;base64,..."（配合 <edit_model>）

    两个工程细节：
      1) 接口返回的是**临时 URL**（s3.siliconflow.cn/temporary/...），会过期，
         所以这里在 Provider 内就把图下载成 bytes 返回，调用方拿到的是稳定产物，
         直接可写入 MinIO，不存在"链接失效"问题。
      2) 图像生成是秒级～十秒级操作，超时单独放宽到 300s，不复用默认的 60s。
    """

    name = "siliconflow:qwen-image"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str = "Qwen/Qwen-Image",
        edit_model: str = "Qwen/Qwen-Image-Edit",
        steps: int = 20,
        guidance: float = 7.5,
    ) -> None:
        _SiliconFlowBase.__init__(self, api_key, base_url, timeout=300.0)
        self.model = model
        self.edit_model = edit_model
        self.steps = steps
        self.guidance = guidance

    # ---------------- 内部 ----------------
    def _download(self, url: str) -> bytes:
        """下载生成结果。走同一套代理策略（trust_env=False）避免代理掐断 TLS。"""
        if url.startswith("data:"):
            return base64.b64decode(url.split(",", 1)[-1])
        with httpx.Client(timeout=180.0, trust_env=self.trust_env) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.content

    def _request(self, model: str, prompt: str, size: str, image: bytes | None) -> bytes:
        body: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "image_size": size,
            "batch_size": 1,
            "num_inference_steps": self.steps,
            "guidance_scale": self.guidance,
        }
        if image is not None:
            # 图生图：接口接受 data URI 形式的内联图，避免再往对象存储传一次
            body["image"] = "data:image/png;base64," + base64.b64encode(image).decode("ascii")
        payload = self._post("/images/generations", json=body).json()
        images = payload.get("images") or []
        if not images:
            raise RuntimeError(f"图像生成未返回结果：{str(payload)[:200]}")
        return self._download(str(images[0].get("url") or images[0].get("image") or ""))

    # ---------------- 对外 ----------------
    def generate_image(self, prompt: str, size: str = "1024x1024", **options: Any) -> bytes:
        return self._request(str(options.get("model") or self.model), prompt, size, None if not options.get("image") else options["image"])

    def edit_image(self, image: bytes, prompt: str, size: str = "1024x1024", **options: Any) -> bytes:
        return self._request(str(options.get("model") or self.edit_model), prompt, size, image)
