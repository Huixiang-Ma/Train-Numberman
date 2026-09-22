"""工单19 · 纪念内容生成 / 攻略流程图 / 产物访问接口

工单编号：人工智能CV-AIGC-19-文旅Agent任务工单-创意策划与内容生成
对应 docs/05 第五章接口表：
  POST /api/v1/create/image   照片艺术化 / 明信片 / 虚拟合影
  POST /api/v1/create/video   短视频 / 电子相册
  POST /api/v1/create/diary   旅行日记
  POST /api/v1/create/guide   活动攻略 + 流程图
  GET  /api/v1/create/assets  我的创作列表
  GET  /api/v1/create/asset/{id}/file  产物字节（前端 <img>/<video> 直用）

异步策略：图像生成实测 30~40s、视频合成 5~15s，默认入 Celery 队列（background=true），
前端按 task_id 轮询；测试或脚本可传 background=false 走同步返回。
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile

from ...core.config import get_settings
from ...db.base import SessionLocal
from ...db.models import CreationTask
from ...providers.registry import get_storage
from ...schemas import ApiResponse, DiaryRequest, GuideRequest, MapRequest
from ...services.activity import ActivityService
from ...services.creation import CreationService
from ...services.creative_common import ContentRejected, read_uri
from ...services.retrieval import RetrievalService

logger = logging.getLogger("wenlv.api.creation")

router = APIRouter(prefix="/create", tags=["creation"])

IMAGE_KINDS = {"artistic", "postcard", "group_photo"}
MAX_UPLOAD_BYTES = 12 * 1024 * 1024  # 单张照片上限 12MB，防止超大图拖垮生成链路


# --------------------------------------------------------------------------
# 配额控制（docs/05 §九：图像/视频生成消耗额度大，需做任务排队与配额控制）
# --------------------------------------------------------------------------
def _check_quota(request: Request) -> None:
    settings = get_settings()
    limit = settings.creation_quota_per_hour
    if limit <= 0:
        return
    owner = (request.client.host if request.client else "unknown") or "unknown"
    try:
        import redis

        client = redis.Redis.from_url(settings.redis_url)
        key = f"wenlv:create:quota:{owner}"
        used = int(client.incr(key))
        if used == 1:
            client.expire(key, 3600)
        if used > limit:
            raise HTTPException(status_code=429, detail=f"生成配额已用尽（每小时 {limit} 次），请稍后再试")
    except HTTPException:
        raise
    except Exception as exc:  # Redis 不可用时放行，不因配额组件故障阻断创作
        logger.warning("配额校验跳过（Redis 不可用）：%s", exc)


async def _store_uploads(files: list[UploadFile]) -> list[str]:
    """把上传的素材写入对象存储，返回 minio:// URI 列表。"""
    storage = get_storage()
    uris: list[str] = []
    for item in files[:4]:  # 虚拟合影最多 4 人，视频相册在服务层另有上限
        raw = await item.read()
        if not raw:
            continue
        if len(raw) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail=f"单张照片不得超过 {MAX_UPLOAD_BYTES // 1024 // 1024}MB")
        media_type = RetrievalService.guess_media_type(item.filename or "")
        if media_type != "image":
            raise HTTPException(status_code=400, detail="仅支持上传图片素材（jpg / png / webp）")
        key = f"creation/source/{uuid.uuid4().hex}-{item.filename or 'upload.jpg'}"
        uris.append(storage.put_object(key, raw, content_type=item.content_type or "image/jpeg"))
    if not uris:
        raise HTTPException(status_code=400, detail="请至少上传一张有效照片")
    return uris


def _submit(kind: str, uris: list[str], options: dict, owner: str) -> dict:
    """登记任务状态并入队，返回 task_id。"""
    from ...tasks.create import create_image_task, create_video_task

    celery_id = uuid.uuid4().hex
    try:
        with SessionLocal() as db:
            db.add(
                CreationTask(
                    celery_task_id=celery_id,
                    kind=kind,
                    status="pending",
                    progress=0,
                    message="已进入队列",
                    params={**options, "sources": len(uris)},
                    owner=owner,
                )
            )
            db.commit()
    except Exception as exc:
        logger.warning("任务登记失败（仍会入队）：%s", exc)

    if kind == "video":
        create_video_task.apply_async(args=[uris, options], task_id=celery_id)
    else:
        create_image_task.apply_async(args=[kind, uris, options], task_id=celery_id)
    return {"task_id": celery_id, "kind": kind, "status": "pending", "progress": 0, "message": "已进入队列"}


# --------------------------------------------------------------------------
# 图像类
# --------------------------------------------------------------------------
@router.post("/image", response_model=ApiResponse)
async def create_image(
    request: Request,
    files: list[UploadFile] = File(...),
    kind: str = Form("artistic"),
    style: str = Form("ink"),
    title: str = Form(""),
    text: str = Form(""),
    place: str = Form(""),
    scene: str = Form(""),
    background: bool = Form(True),
) -> ApiResponse:
    """照片艺术化 / 明信片 / 虚拟合影。

    kind: artistic（艺术化纪念照）| postcard（明信片）| group_photo（虚拟合影）
    """
    if kind not in IMAGE_KINDS:
        raise HTTPException(status_code=400, detail=f"不支持的 kind：{kind}（可选 {'/'.join(sorted(IMAGE_KINDS))}）")
    _check_quota(request)

    uris = await _store_uploads(files)
    options = {"style": style, "title": title, "text": text, "place": place, "scene": scene}
    owner = (request.client.host if request.client else "guest") or "guest"

    if background:
        return ApiResponse(data=_submit(kind, uris, options, owner), trace_id=uuid.uuid4().hex)

    try:
        service = CreationService()
        if kind == "artistic":
            asset = service.artistic(read_uri(uris[0]), style, title)
        elif kind == "postcard":
            asset = service.postcard(read_uri(uris[0]), text=text, place=place, title=title, style=style)
        else:
            asset = service.group_photo([read_uri(u) for u in uris], scene, title)
    except ContentRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("纪念图片生成失败：%s", exc)
        raise HTTPException(status_code=500, detail=f"生成失败：{exc}") from exc
    return ApiResponse(data=asset, trace_id=uuid.uuid4().hex)


# --------------------------------------------------------------------------
# 视频类
# --------------------------------------------------------------------------
@router.post("/video", response_model=ApiResponse)
async def create_video(
    request: Request,
    files: list[UploadFile] = File(...),
    title: str = Form("我的旅行回忆"),
    captions: str = Form(""),
    seconds_per_image: float = Form(0),
    watermark: str = Form("文旅创新智脑"),
    with_narration: bool = Form(False),
    background: bool = Form(True),
) -> ApiResponse:
    """把旅行照片合成为短视频 / 电子相册（配乐可选 CosyVoice 解说）。"""
    _check_quota(request)
    uris = await _store_uploads(files)
    caption_list = [c.strip() for c in captions.replace("\n", "|").split("|") if c.strip()]
    options = {
        "title": title,
        "captions": caption_list,
        "seconds_per_image": seconds_per_image or None,
        "watermark": watermark,
        "with_narration": with_narration,
    }
    owner = (request.client.host if request.client else "guest") or "guest"

    if background:
        return ApiResponse(data=_submit("video", uris, options, owner), trace_id=uuid.uuid4().hex)

    try:
        asset = CreationService().video(
            [read_uri(u) for u in uris],
            title=title,
            captions=caption_list,
            seconds_per_image=seconds_per_image or None,
            watermark=watermark,
            with_narration=with_narration,
        )
    except ContentRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("短视频合成失败：%s", exc)
        raise HTTPException(status_code=500, detail=f"合成失败：{exc}") from exc
    return ApiResponse(data=asset, trace_id=uuid.uuid4().hex)


# --------------------------------------------------------------------------
# 文本类
# --------------------------------------------------------------------------
@router.post("/diary", response_model=ApiResponse)
def create_diary(payload: DiaryRequest) -> ApiResponse:
    """生成旅行日记（纯文本，秒级返回，不入队）。"""
    try:
        asset = CreationService().diary(
            title=payload.title, tone=payload.tone, place=payload.place, highlights=payload.highlights
        )
    except ContentRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ApiResponse(data=asset, trace_id=uuid.uuid4().hex)


@router.post("/guide", response_model=ApiResponse)
def create_guide(payload: GuideRequest) -> ApiResponse:
    """活动参与攻略 + 体验流程图（Mermaid 源码 + 位图）。"""
    try:
        data = ActivityService().guide(payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ContentRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("攻略生成失败：%s", exc)
        raise HTTPException(status_code=500, detail=f"攻略生成失败：{exc}") from exc
    return ApiResponse(data=data, trace_id=uuid.uuid4().hex)


# --------------------------------------------------------------------------
# 导览地图 / 活动回顾 PPT（工单20 典型场景 13 / 12）
# --------------------------------------------------------------------------
@router.post("/map", response_model=ApiResponse)
def create_map(payload: MapRequest) -> ApiResponse:
    """按行程分站生成可下载打印的导览地图（坐标取自 PostGIS 真实景点数据）。"""
    try:
        stops = [{"name": item.name, "index": item.index} for item in payload.stops]
        asset = CreationService().guide_map(stops, payload.title, payload.subtitle)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("导览地图生成失败：%s", exc)
        raise HTTPException(status_code=500, detail=f"导览地图生成失败：{exc}") from exc
    return ApiResponse(data=asset, trace_id=uuid.uuid4().hex)


@router.post("/ppt", response_model=ApiResponse)
async def create_ppt(
    files: list[UploadFile] = File(...),
    title: str = Form("活动回顾"),
    subtitle: str = Form(""),
    notes: str = Form(""),
) -> ApiResponse:
    """把活动照片整理成回顾 PPT（封面 + 每图一页 + 结尾页）。"""
    uris = await _store_uploads(files)
    note_list = [item.strip() for item in notes.replace("\n", "|").split("|")]
    try:
        asset = CreationService().review_ppt(
            [read_uri(uri) for uri in uris], title=title, notes=note_list, subtitle=subtitle
        )
    except Exception as exc:
        logger.exception("活动回顾 PPT 生成失败：%s", exc)
        raise HTTPException(status_code=500, detail=f"PPT 生成失败：{exc}") from exc
    return ApiResponse(data=asset, trace_id=uuid.uuid4().hex)


# --------------------------------------------------------------------------
# 产物访问
# --------------------------------------------------------------------------
@router.get("/assets", response_model=ApiResponse)
def list_assets(kind: str | None = None, limit: int = 20) -> ApiResponse:
    """我的创作列表（按创建时间倒序）。"""
    return ApiResponse(data=CreationService().list_assets(kind=kind, limit=limit), trace_id=uuid.uuid4().hex)


@router.get("/asset/{asset_id}/file")
def asset_file(asset_id: str) -> Response:
    """产物字节。

    由后端代理转发而不是回 MinIO 预签名地址：预签名链接会过期、且要求浏览器
    能直连 MinIO 端口（跨源 + 端口暴露）。走 /api 代理后前端 <img> / <video> 直接可用。
    内容以 32 位随机 id 寻址，不可枚举。
    """
    asset = CreationService().get_asset(asset_id)
    if asset is None or not asset.result_uri:
        raise HTTPException(status_code=404, detail="产物不存在")
    data = read_uri(asset.result_uri)
    filename = f"{asset.kind}-{asset.id}.{'mp4' if 'video' in (asset.result_mime or '') else 'bin'}"
    return Response(
        content=data,
        media_type=asset.result_mime or "application/octet-stream",
        headers={"Cache-Control": "public, max-age=86400", "Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/task/{task_id}", response_model=ApiResponse)
def task_status(task_id: str) -> ApiResponse:
    """轮询异步生成任务；成功后直接带回产物，前端一次请求即可拿到结果。"""
    from sqlalchemy import select

    with SessionLocal() as db:
        row = db.scalars(select(CreationTask).where(CreationTask.celery_task_id == task_id)).first()
        if row is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        payload = {
            "task_id": task_id,
            "kind": row.kind,
            "status": row.status,
            "progress": row.progress,
            "message": row.message,
            "error": row.error,
            "asset": None,
        }
        if row.asset_id:
            asset = CreationService().get_asset(row.asset_id)
            if asset is not None:
                payload["asset"] = CreationService.to_out(asset)
    return ApiResponse(data=payload, trace_id=uuid.uuid4().hex)
