"""工单19 · AIGC 内容生成异步任务

工单编号：人工智能CV-AIGC-19-文旅Agent任务工单-创意策划与内容生成
对应 docs/05 §五：AIGC 任务耗时长（实测图生图 30~40s、视频合成 5~15s），
统一走 **Celery + Redis** 异步队列，生成结果存对象存储。

为什么还要一张 creation_task 表：
  Celery 的 result backend 只解决"结果可取"，无法支撑「我的创作」列表、
  失败原因回看与配额统计，因此额外落一份任务状态；两者以 celery_task_id 关联。
"""
from __future__ import annotations

import logging
from typing import Any

from ..db.base import SessionLocal
from ..db.models import CreationTask
from ..services.creative_common import read_uri
from .celery_app import celery_app

logger = logging.getLogger("wenlv.tasks.create")


def _mark(celery_task_id: str, status: str, progress: int, message: str, asset_id: str | None = None, error: str = "") -> None:
    """更新任务状态；任何异常都不应影响生成主流程。"""
    try:
        with SessionLocal() as db:
            from sqlalchemy import select

            row = db.scalars(select(CreationTask).where(CreationTask.celery_task_id == celery_task_id)).first()
            if row is None:
                return
            row.status = status
            row.progress = progress
            row.message = message[:256]
            if asset_id:
                row.asset_id = asset_id
            if error:
                row.error = error[:1000]
            db.commit()
    except Exception as exc:
        logger.warning("更新任务状态失败：%s", exc)


def _load(uris: list[str]) -> list[bytes]:
    return [read_uri(uri) for uri in uris]


@celery_app.task(bind=True, name="create.image")
def create_image_task(
    self,
    kind: str,
    source_uris: list[str],
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """纪念图片类任务：artistic（艺术化）/ postcard（明信片）/ group_photo（虚拟合影）。"""
    options = options or {}
    task_id = self.request.id or ""
    try:
        _mark(task_id, "running", 15, "正在读取素材")
        self.update_state(state="PROGRESS", meta={"progress": 15, "message": "正在读取素材"})

        from ..services.creation import CreationService

        service = CreationService()
        images = _load(source_uris)
        if not images:
            raise ValueError("未获取到可用素材")

        _mark(task_id, "running", 40, "正在调用图像生成模型")
        self.update_state(state="PROGRESS", meta={"progress": 40, "message": "正在生成"})

        if kind == "artistic":
            asset = service.artistic(images[0], options.get("style", "ink"), options.get("title", ""))
        elif kind == "postcard":
            asset = service.postcard(
                images[0],
                text=options.get("text", ""),
                place=options.get("place", ""),
                title=options.get("title", ""),
                style=options.get("style", "ink"),
            )
        elif kind == "group_photo":
            asset = service.group_photo(images, options.get("scene", ""), options.get("title", ""))
        else:
            raise ValueError(f"不支持的图片任务类型：{kind}")

        _mark(task_id, "success", 100, "已完成", asset_id=asset.get("id") or None)
        return {"kind": kind, "asset": asset}
    except Exception as exc:
        logger.exception("图片生成任务失败：%s", exc)
        _mark(task_id, "failed", 100, "生成失败", error=str(exc))
        raise


@celery_app.task(bind=True, name="create.video")
def create_video_task(self, source_uris: list[str], options: dict[str, Any] | None = None) -> dict[str, Any]:
    """短视频 / 电子相册任务：FFmpeg 运镜 + 交叉淡入 + 字幕（可选解说音轨）。"""
    options = options or {}
    task_id = self.request.id or ""
    try:
        _mark(task_id, "running", 15, "正在读取照片")
        self.update_state(state="PROGRESS", meta={"progress": 15, "message": "正在读取照片"})

        from ..services.creation import CreationService

        images = _load(source_uris)
        if not images:
            raise ValueError("未获取到可用照片")

        _mark(task_id, "running", 45, "正在合成短片")
        self.update_state(state="PROGRESS", meta={"progress": 45, "message": "正在合成短片"})

        asset = CreationService().video(
            images,
            title=options.get("title", "我的旅行回忆"),
            captions=options.get("captions") or [],
            seconds_per_image=options.get("seconds_per_image"),
            watermark=options.get("watermark", "文旅创新智脑"),
            with_narration=bool(options.get("with_narration")),
        )
        _mark(task_id, "success", 100, "已完成", asset_id=asset.get("id") or None)
        return {"kind": "video", "asset": asset}
    except Exception as exc:
        logger.exception("视频合成任务失败：%s", exc)
        _mark(task_id, "failed", 100, "合成失败", error=str(exc))
        raise


@celery_app.task(name="create.diary")
def create_diary_task(options: dict[str, Any] | None = None) -> dict[str, Any]:
    """旅行日记任务：纯文本生成，耗时短，但仍与图片/视频统一走队列便于前端轮询。"""
    options = options or {}
    from ..services.creation import CreationService

    asset = CreationService().diary(
        image_count=int(options.get("image_count") or 0),
        title=options.get("title", "我的旅行日记"),
        tone=options.get("tone", "温暖记录"),
        place=options.get("place", ""),
        highlights=options.get("highlights") or [],
        captions=options.get("captions") or [],
    )
    return {"kind": "diary", "asset": asset}
