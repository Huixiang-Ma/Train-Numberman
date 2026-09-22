"""工单17 · 应用入口

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成
启动：uvicorn app.main:app --host 127.0.0.1 --port 8100
"""
from __future__ import annotations

import json
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .api.v1.router import api_router
from .core.config import get_settings
from .core.observability import (
    TRACE_HEADER,
    Stopwatch,
    log_access,
    new_trace_id,
    record_audit,
    reset_trace_id,
    set_trace_id,
)
from .db.base import create_all

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("wenlv")

SEED_FILE = Path(__file__).resolve().parent / "data" / "kb_seed.json"


def _seed_if_empty() -> None:
    """仅当知识库为空时灌入示例数据。

    先查库再决定是否构造 KBService，避免已有数据时仍然加载 BGE-M3 / Chinese-CLIP。
    """
    try:
        from sqlalchemy import func, select

        from .db.base import SessionLocal
        from .db.models import KbChunk

        with SessionLocal() as db:
            count = int(db.scalar(select(func.count()).select_from(KbChunk)) or 0)
        if count > 0:
            logger.info("知识库已有 %d 条，跳过示例灌入", count)
            return
        if not SEED_FILE.exists():
            return

        import uuid

        from .providers.base import KbChunkData
        from .services.kb import KBService

        items = json.loads(SEED_FILE.read_text(encoding="utf-8"))
        chunks = [
            KbChunkData(
                id=item.get("id") or uuid.uuid4().hex,
                title=item["title"],
                content=item["content"],
                modality=item.get("modality", "text"),
                media_uri=item.get("media_uri"),
                tags=list(item.get("tags") or []),
                source=item.get("source", ""),
                authority=item.get("authority", ""),
            )
            for item in items
        ]
        result = KBService().ingest(chunks, document_title="示例文旅知识库", source="示例数据")
        logger.info("示例知识库已灌入：%s", result)
    except Exception as exc:  # 启动阶段不因灌库失败而中断
        logger.warning("示例知识库灌入跳过：%s: %s", type(exc).__name__, exc)


def _warmup_providers() -> None:
    """在主线程预热重模型。

    首次请求才惰性加载会带来两个问题：
      1) 首个请求要额外等待模型加载（Chinese-CLIP 等可达数十秒）；
      2) transformers 的惰性导入在工作线程中首次并发触发时可能抛
         ImportError（见 deploy/logs/uvicorn.err.log），使该次请求直接失败。
    预热在启动阶段完成，任一能力失败都只记告警、不阻断启动。
    """
    try:
        from .providers.registry import (
            get_clip,
            get_embedding,
            get_llm,
            get_reranker,
            get_text_store,
        )
    except Exception as exc:  # 装配层不可用时放弃预热
        logger.warning("能力预热跳过：装配层不可用 %s: %s", type(exc).__name__, exc)
        return

    for name, getter in (
        ("embedding(BGE-M3)", get_embedding),
        ("clip(Chinese-CLIP)", get_clip),
        ("reranker(bge-reranker-v2-m3)", get_reranker),
        ("llm(Qwen)", get_llm),
        ("vector-store(Milvus)", get_text_store),
    ):
        try:
            getter()
            logger.info("能力预热完成：%s", name)
        except Exception as exc:
            logger.warning("能力预热失败 %s：%s: %s", name, type(exc).__name__, exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    try:
        create_all()
        logger.info("数据库表已就绪（schema=%s）", settings.db_schema)
    except Exception as exc:
        logger.error("数据库初始化失败：%s: %s", type(exc).__name__, exc)
    _seed_if_empty()
    if settings.warmup_providers:
        _warmup_providers()
    logger.info("启动完成 | 工单=%s", settings.work_order)
    yield
    logger.info("服务关闭")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description=(
            "多模态文旅知识检索与生成系统（工单17）。"
            "技术栈：FastAPI + LangGraph + Milvus + BGE-M3 + Chinese-CLIP + bge-reranker-v2 + "
            "Qwen + PaddleOCR + FunASR + CosyVoice + PostgreSQL/PostGIS + Redis + MinIO。"
        ),
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix=settings.api_prefix)

    @app.middleware("http")
    async def observability_middleware(request: Request, call_next):
        """全链路可观测（工单20）：trace_id 贯穿 + 访问日志 + 操作审计。

        为什么放在中间件而不是各路由：
          trace_id 需要在「进入路由之前」就确定，才能覆盖路由内生成的内容、
          异常出口与审计记录；放在中间件里，一个 id 就能把访问日志、审计记录、
          异常堆栈和响应体串成一条链，排障时不必靠时间戳猜关联。
        """
        trace_id = request.headers.get(TRACE_HEADER) or new_trace_id()
        token = set_trace_id(trace_id)
        watch = Stopwatch()
        client_ip = request.client.host if request.client else ""
        try:
            response = await call_next(request)
        except Exception:
            log_access(request.method, request.url.path, 500, watch.ms, client_ip)
            reset_trace_id(token)
            raise
        log_access(request.method, request.url.path, response.status_code, watch.ms, client_ip)
        # 审计写库放到线程池，避免同步 IO 阻塞事件循环
        await run_in_threadpool(record_audit, request.method, request.url.path, response.status_code, client_ip)
        response.headers[TRACE_HEADER] = trace_id
        reset_trace_id(token)
        return response

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """统一异常出口：把内部异常转成可读信息，避免前端只看到 500。

        上游模型服务是外网依赖，网络抖动会以 httpx 异常形式冒到这一层；
        这里明确区分「上游网络问题」与「服务内部异常」，并带上 trace_id 便于对日志。
        """
        from .core.observability import get_trace_id

        trace_id = get_trace_id() or uuid.uuid4().hex[:16]
        logger.exception(
            "未处理异常 trace_id=%s path=%s %s: %s",
            trace_id,
            request.url.path,
            type(exc).__name__,
            exc,
        )
        if isinstance(exc, (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError, httpx.TransportError)):
            message = "上游模型服务网络不稳定，自动重试后仍未成功，请稍后重新发送"
        else:
            message = f"服务内部异常（{type(exc).__name__}），请稍后重试"
        return JSONResponse(
            status_code=500,
            content={"code": 5001, "message": message, "detail": message, "data": None, "trace_id": trace_id},
        )

    @app.get("/", tags=["meta"])
    def root() -> dict:
        return {
            "code": 0,
            "message": "ok",
            "data": {
                "name": settings.app_name,
                "work_order": settings.work_order,
                "docs": "/docs",
                "api_prefix": settings.api_prefix,
            },
        }

    return app


app = create_app()
