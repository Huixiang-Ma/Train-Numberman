"""工单17 · Celery 应用（Celery + Redis）

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成
启动：celery -A app.tasks.celery_app worker --loglevel=info --pool=solo
"""
from __future__ import annotations

from celery import Celery

from ..core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "wenlv",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    # 工单19 新增 app.tasks.create：AIGC 图像/视频/日记生成任务
    include=["app.tasks.ingest", "app.tasks.create"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=False,
    task_track_started=True,
    worker_hijack_root_logger=False,
    # 单 worker 串行执行：图像生成占用外部额度、视频合成占用 CPU，
    # 并发执行只会互相拖慢并放大限流风险（docs/05 §九 生成算力成本提示）
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)
