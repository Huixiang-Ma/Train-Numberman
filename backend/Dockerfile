# 文旅创新智脑 · 后端镜像
# 工单编号：人工智能CV-AIGC-20-文旅Agent任务工单-功能集成测试与部署
#
# 依据 docs/01 §六：容器化 Docker + 编排（开发用 Docker Compose，生产 K8s）。
#
# 镜像体积说明：本服务需要 PyTorch（Chinese-CLIP）与 PaddlePaddle（PaddleOCR）
# 两个本地推理框架，基础依赖约 3~5GB。**模型权重不打进镜像**，而是通过卷挂载
# （见 deploy/docker-compose.app.yml），这样模型热更新只需替换宿主目录，符合
# docs/01 §六「模型热更新：模型仓库 + 滚动重载」的要求。
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Shanghai \
    # 与 core/config.py 保持一致：HF 直连不可用时走镜像；关闭 Paddle 的 MKLDNN
    HF_ENDPOINT=https://hf-mirror.com \
    FLAGS_use_mkldnn=0

# ffmpeg：工单19/20 的视频合成（docs/01 §4.7 FFmpeg + OpenCV）
# libgl1 / libglib2.0-0：OpenCV 与 MediaPipe 的运行时依赖（headless 亦需 glib）
# curl：容器健康检查
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
        curl \
        fonts-wqy-zenhei \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts

# 模型与数据目录由编排挂载：
#   /models  Chinese-CLIP / YOLO11 / SAM 2 / MediaPipe 权重
#   /app/.env 运行时配置（含 API Key，不要打进镜像）
ENV MODEL_DIR=/models \
    MEDIAPIPE_MODEL_DIR=/models/mediapipe \
    YOLO_DET_MODEL=/models/yolo11n.pt \
    YOLO_CLS_MODEL=/models/yolo11n-cls.pt \
    SAM_MODEL=/models/sam2.1_t.pt \
    CLIP_PATH=/models/chinese-clip

EXPOSE 8100

# 就绪探针：内置的 readyz 会真实探测 PostgreSQL / Redis / Milvus / MinIO
HEALTHCHECK --interval=30s --timeout=10s --start-period=180s --retries=5 \
    CMD curl -fsS http://127.0.0.1:8100/api/v1/readyz || exit 1

# 生产建议以多 worker 提升并发（docs/06 §4.2 高并发与弹性扩展）：
#   CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100", "--workers", "4"]
# 注意：每个 worker 都会各自加载一次本地模型权重，需按内存容量调整 worker 数。
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
