"""工单17 · 能力适配层接口

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成
所有实现严格对应 docs/01-技术栈选型总表的主选技术，不再提供替代实现。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Sequence


@dataclass
class KbChunkData:
    """入库/检索使用的最小知识单元。"""

    id: str
    title: str
    content: str
    modality: str = "text"
    media_uri: str | None = None
    tags: list[str] = field(default_factory=list)
    source: str = ""
    authority: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Hit:
    chunk: KbChunkData
    score: float
    rerank_score: float | None = None


class EmbeddingProvider(ABC):
    """文本向量化（BGE-M3）。"""

    name: str = "bge-m3"
    dim: int = 1024

    @abstractmethod
    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]: ...

    @abstractmethod
    def embed_query(self, text: str) -> list[float]: ...


class ClipProvider(ABC):
    """图文向量化（Chinese-CLIP），文本与图像共享向量空间。"""

    name: str = "chinese-clip"
    dim: int = 512

    @abstractmethod
    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]: ...

    @abstractmethod
    def embed_images(self, images: Sequence[bytes]) -> list[list[float]]: ...


class RerankerProvider(ABC):
    """重排序（bge-reranker-v2）。"""

    name: str = "bge-reranker-v2"

    @abstractmethod
    def rerank(self, query: str, candidates: Sequence[str], top_n: int) -> list[tuple[int, float]]: ...


class VectorStore(ABC):
    """向量数据库（Milvus，HNSW）。"""

    name: str = "milvus"

    @abstractmethod
    def upsert(self, items: Sequence[KbChunkData], vectors: Sequence[Sequence[float]]) -> int: ...

    @abstractmethod
    def search(
        self,
        vector: Sequence[float],
        top_k: int,
        modality: str | None = None,
        tags: Sequence[str] | None = None,
    ) -> list[Hit]: ...

    @abstractmethod
    def delete(self, ids: Sequence[str]) -> int: ...

    @abstractmethod
    def count(self) -> int: ...


class LLMProvider(ABC):
    """生成模型（Qwen，国产合规主选）。"""

    name: str = "qwen"

    @abstractmethod
    def generate(self, prompt: str, system: str | None = None, max_new_tokens: int | None = None) -> str: ...


class OCRProvider(ABC):
    name: str = "paddleocr"

    @abstractmethod
    def recognize(self, image: bytes) -> list[tuple[str, float]]: ...


class ASRProvider(ABC):
    name: str = "funasr"

    @abstractmethod
    def transcribe(self, audio: bytes, mime: str = "audio/wav") -> str: ...


class TTSProvider(ABC):
    name: str = "cosyvoice"

    @abstractmethod
    def synthesize(self, text: str, lang: str = "zh", voice: str = "default") -> dict[str, Any]: ...


class ObjectStorage(ABC):
    name: str = "minio"

    @abstractmethod
    def put_object(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str: ...

    @abstractmethod
    def get_object(self, key: str) -> bytes: ...

    @abstractmethod
    def presigned_url(self, key: str, expires_seconds: int = 3600) -> str: ...


# ==========================================================================
# 阶段四（工单19）· AIGC 内容生成能力
# 对应 docs/01 §4.7：图像生成（通义万相 / Stable Diffusion）、风格迁移
# （IP-Adapter / ControlNet）、视频合成（FFmpeg + OpenCV）、流程图（Mermaid / Graphviz）
# ==========================================================================
class ImageProvider(ABC):
    """图像生成与风格迁移。

    工单19 §3.2：照片艺术化、明信片、虚拟合影。
    - generate_image：文生图，用于海报底图 / 景区元素合成
    - edit_image：图生图（照片 + 指令），用于风格迁移与画面改造
    """

    name: str = "qwen-image"

    @abstractmethod
    def generate_image(self, prompt: str, size: str = "1024x1024", **options: Any) -> bytes: ...

    @abstractmethod
    def edit_image(self, image: bytes, prompt: str, size: str = "1024x1024", **options: Any) -> bytes: ...


class VideoComposer(ABC):
    """视频合成（FFmpeg + OpenCV）。

    工单19 §3.2：把照片/视频合成为电子相册、旅行短片。
    只负责"合成"这一确定性的工程环节；文案与解说音轨由调用方（服务层）提供，
    因此该能力不依赖任何外部模型，可离线稳定复现。
    """

    name: str = "ffmpeg"

    @abstractmethod
    def compose(
        self,
        images: Sequence[bytes],
        seconds_per_image: float = 2.6,
        captions: Sequence[str] | None = None,
        audio: bytes | None = None,
        width: int = 1280,
        height: int = 720,
        watermark: str = "",
    ) -> bytes: ...


class DiagramRenderer(ABC):
    """流程图渲染（Mermaid 源码 + 位图成品）。

    工单19 §4.3：活动参与流程、体验流程图。
    同时给出 Mermaid 源码供前端二次编辑，与位图便于直接下载分享。
    """

    name: str = "mermaid"

    @abstractmethod
    def render(self, title: str, steps: Sequence[str], direction: str = "TD") -> dict[str, Any]: ...
