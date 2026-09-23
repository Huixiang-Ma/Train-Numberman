"""工单17 · 全局配置

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成
配置项严格对应 docs/01-技术栈选型总表：PostgreSQL+PostGIS / Redis / Milvus / MinIO /
BGE-M3 / Chinese-CLIP / bge-reranker-v2 / Qwen / PaddleOCR / FunASR / CosyVoice。
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 模型权重统一走镜像（HuggingFace 直连不可用；见 deploy/models/download_models.py）
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

# PaddlePaddle 3.x 的 oneDNN 指令转换在部分 CPU 后端上不支持某些算子，OCR 预测会抛
#   NotImplementedError: ConvertPirAttribute2RuntimeAttribute not support
#     [pir::ArrayAttribute<pir::DoubleAttribute>]
# 关闭 MKLDNN 走原生 CPU 内核即可绕过。OCR 仍是 PaddleOCR 本地实现（docs/01 主选），
# 只是推理后端从 MKLDNN 切到原生内核，不涉及替代实现。
os.environ.setdefault("FLAGS_use_mkldnn", "0")

# backend/ 目录
BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(BASE_DIR / ".env"), extra="ignore")

    app_name: str = "文旅创新智脑 · 多模态文旅知识检索与生成"
    api_prefix: str = "/api/v1"
    debug: bool = True

    # 工单编号留痕
    work_order: str = "人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成"

    # ---------------- 数据层 ----------------
    database_url: str = "postgresql+psycopg2://wenlv:wenlv_pass@127.0.0.1:5432/wenlv"
    db_schema: str = "wenlv"

    redis_url: str = "redis://127.0.0.1:6379/0"
    celery_broker_url: str = "redis://127.0.0.1:6379/1"
    celery_result_backend: str = "redis://127.0.0.1:6379/2"

    milvus_uri: str = "http://127.0.0.1:19530"
    milvus_collection: str = "wenlv_kb"
    milvus_metric: str = "COSINE"
    milvus_index_type: str = "HNSW"
    milvus_hnsw_m: int = 16
    milvus_hnsw_ef_construction: int = 200
    milvus_search_ef: int = 64

    minio_endpoint: str = "127.0.0.1:9000"
    minio_access_key: str = "wenlv"
    minio_secret_key: str = "wenlv_minio_pass"
    minio_bucket: str = "wenlv-media"
    minio_secure: bool = False

    # ---------------- 模型 ----------------
    model_dir: str = "../models"
    # 默认指向本机已有权重（ModelScope / HuggingFace 缓存），避免重复下载
    bge_m3_path: str = r"C:/Users/17835/.cache/modelscope/hub/BAAI/bge-m3"
    clip_path: str = "../models/chinese-clip"
    reranker_path: str = (
        r"C:/Users/17835/.cache/huggingface/hub/models--BAAI--bge-reranker-v2-m3"
        r"/snapshots/953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
    )

    qwen_serving: str = "local"  # local | vllm
    qwen_model_path: str = (
        r"C:/Users/17835/.cache/huggingface/hub/models--Qwen--Qwen2.5-1.5B-Instruct"
        r"/snapshots/989aa7980e4cf806f80c7fef2b1adb7bc71aa306"
    )
    qwen_base_url: str = "http://127.0.0.1:8000/v1"
    qwen_api_key: str = ""
    qwen_model: str = "qwen-plus"
    qwen_max_new_tokens: int = 512

    paddleocr_lang: str = "ch"
    paddleocr_use_gpu: bool = False
    funasr_model: str = "paraformer-zh"
    cosyvoice_endpoint: str = "http://127.0.0.1:9880"

    # ---------------- 硅基流动 SiliconFlow API ----------------
    # BGE-M3 / Qwen / FunASR(SenseVoice) / bge-reranker-v2-m3 / CosyVoice 统一走该 API
    siliconflow_api_key: str = ""
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    sf_embedding_model: str = "BAAI/bge-m3"
    sf_embedding_dim: int = 1024
    sf_reranker_model: str = "BAAI/bge-reranker-v2-m3"
    sf_llm_model: str = "Qwen/Qwen2.5-7B-Instruct"
    sf_asr_model: str = "FunAudioLLM/SenseVoiceSmall"
    sf_tts_model: str = "FunAudioLLM/CosyVoice2-0.5B"
    sf_tts_voice: str = "FunAudioLLM/CosyVoice2-0.5B:anna"

    # 出网健壮性（工单17 · 稳定性）
    # trust_env=False：调用 SiliconFlow 时忽略 HTTP(S)_PROXY 环境变量。
    # 系统代理会掐断到 api.siliconflow.cn 的 TLS 握手，导致
    # [SSL: UNEXPECTED_EOF_WHILE_READING]（见 deploy/logs/uvicorn.err.log）。
    siliconflow_trust_env: bool = False
    # 瞬时网络故障（连接重置 / 超时 / 429 / 5xx）的自动重试次数
    siliconflow_max_retries: int = 3
    # 启动时预热重模型（BGE-M3 / Chinese-CLIP / Reranker / LLM / 向量库）：
    # 避免首个请求既等模型加载、又在工作线程里首次触发 transformers 惰性导入而报错
    warmup_providers: bool = True

    # 各能力取用方式：cloud=SiliconFlow API（默认）| local=本地权重
    embedding_mode: str = "cloud"
    reranker_mode: str = "cloud"
    llm_mode: str = "cloud"
    asr_mode: str = "cloud"
    tts_mode: str = "cloud"
    clip_mode: str = "local"  # Chinese-CLIP 无同名云端模型，保留本地权重

    # ================= 阶段三（工单18）=================

    # ---------------- CV 深度图像任务 ----------------
    mediapipe_model_dir: str = "../models/mediapipe"
    yolo_det_model: str = "../models/yolo11n.pt"      # 目标检测 + ByteTrack 跟踪
    yolo_cls_model: str = "../models/yolo11n-cls.pt"  # 图像分类
    sam_model: str = "../models/sam2.1_t.pt"          # SAM 2 图像分割
    detect_conf: float = 0.35

    # ---------------- 会话（Redis 主选）----------------
    session_provider: str = "redis"  # redis | memory
    session_ttl_seconds: int = 3600
    session_max_turns: int = 20

    # ---------------- 数字人 ----------------
    avatar_id: str = "qingci"
    avatar_name: str = "青瓷"
    avatar_emotion: str = "calm"
    # 视觉交互：连续稳定帧、同目标自动讲解冷却及知识库召回数量
    avatar_stable_frames: int = 3
    avatar_auto_explain_cooldown_seconds: float = 20.0
    avatar_auto_explain_top_k: int = 3
    # viseme：输出视位序列由前端 Three.js 驱动（CPU 环境默认）
    # musetalk：调用 GPU 唇形服务生成视频
    lipsync_provider: str = "viseme"
    musetalk_endpoint: str = "http://127.0.0.1:8080"

    # ---------------- 检索 ----------------
    top_k: int = 10
    rerank_top_n: int = 3

    # ---------------- 安全 ----------------
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 120
    admin_username: str = "admin"
    admin_password: str = "wenlv_admin_pass"

    # 内容安全词表：逗号分隔（留空表示不启用）；避免空值导致列表解析失败。
    # 工单20 §4.6 要求「自动 + 人工结合的内容审核」——机制早已具备，但默认词表为空
    # 时等于只有开关没有内容，合规自查会如实标为 pending。这里给出类别级默认词表。
    content_blocklist: str = "赌博,毒品,暴力,色情,诈骗,枪支,违禁品,传销"

    # ================= 阶段四（工单19）=================

    # ---------------- AIGC 内容生成 ----------------
    # 图像生成 / 风格迁移（docs/01 §4.7 主选「通义万相 / Stable Diffusion」）。
    # 本项目取用通义系云端模型（Qwen-Image 系列），与 BGE-M3 / Qwen / CosyVoice
    # 一致的取用方式：模型不本地驻留（本机无 GPU，本地 SD 推理不可行）。
    image_mode: str = "cloud"
    sf_image_model: str = "Qwen/Qwen-Image"           # 文生图：海报底图、景区元素
    sf_image_edit_model: str = "Qwen/Qwen-Image-Edit"  # 图生图：照片艺术化、明信片
    sf_image_steps: int = 20
    sf_image_guidance: float = 7.5

    # ---------------- 视频合成（FFmpeg + OpenCV）----------------
    ffmpeg_bin: str = "ffmpeg"
    video_width: int = 1280
    video_height: int = 720
    video_seconds_per_image: float = 2.6
    video_max_images: int = 12

    # ---------------- 生成产物 / 分享 ----------------
    creation_prefix: str = "creation"
    # 分享链接前端可达地址（Web 端为 Vite 开发服务端口）
    share_base_url: str = "http://127.0.0.1:8200/share"
    share_ttl_seconds: int = 604800
    # 生成任务配额（工单19 §九「生成算力成本」风险提示：需做配额控制）
    creation_quota_per_hour: int = 60

    # ---------------- 路径解析 ----------------
    def resolve(self, relative: str) -> Path:
        """把 .env 中的相对路径解析为基于 backend/ 的绝对路径。"""
        path = Path(relative)
        return path if path.is_absolute() else (BASE_DIR / path).resolve()

    @property
    def model_dir_path(self) -> Path:
        return self.resolve(self.model_dir)

    def locate_model(self, value: str) -> str:
        """把配置值解析为可直接传给模型库的本地路径或仓库 ID。

        优先级：绝对路径存在 → 相对 backend/ 的路径存在 → 原样作为仓库 ID（交由模型缓存解析）。
        """
        if not value:
            return value
        direct = Path(value)
        if direct.is_absolute() and direct.exists():
            return str(direct)
        resolved = (BASE_DIR / value).resolve()
        if resolved.exists():
            return str(resolved)
        if direct.exists():
            return str(direct.resolve())
        return value

    @property
    def bge_m3_dir(self) -> str:
        return self.locate_model(self.bge_m3_path)

    @property
    def clip_dir(self) -> str:
        return self.locate_model(self.clip_path)

    @property
    def qwen_dir(self) -> str:
        return self.locate_model(self.qwen_model_path)

    @property
    def reranker(self) -> str:
        return self.locate_model(self.reranker_path)

    @property
    def mediapipe_dir(self) -> Path:
        return self.resolve(self.mediapipe_model_dir)

    @property
    def det_weights(self) -> str:
        return self.locate_model(self.yolo_det_model)

    @property
    def cls_weights(self) -> str:
        return self.locate_model(self.yolo_cls_model)

    @property
    def sam_weights(self) -> str:
        return self.locate_model(self.sam_model)

    @property
    def blocklist(self) -> list[str]:
        return [x.strip() for x in (self.content_blocklist or "").split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
