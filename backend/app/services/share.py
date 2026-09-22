"""工单19 · 多模态内容输出与分享

工单编号：人工智能CV-AIGC-19-文旅Agent任务工单-创意策划与内容生成
对应 docs/05 §3.4 / §4.4：生成内容可一键保存、下载或分享到社交平台。

实现要点：
  - 分享链接用**随机 token**而不是自增 id，避免被枚举遍历（内容多为游客个人照片）。
  - 分享页地址用**查询参数**（?share=token）而非路径段：前端为单页应用，
    无路由库，查询参数由 URLSearchParams 直接读取，不依赖服务端 rewrite。
  - 分享海报为服务端合成的成品图：视频类取首帧作为封面。
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Any

from PIL import Image, ImageDraw

from ..core.config import get_settings
from ..db.base import SessionLocal
from ..db.models import CreationAsset, ItineraryPlan, ShareLink
from .creative_common import asset_file_url, check_text, read_uri, store_bytes

logger = logging.getLogger("wenlv.share")


def _video_first_frame(data: bytes) -> Image.Image | None:
    """用 OpenCV 抽取视频首帧作为海报封面（docs/01 §4.7 FFmpeg + OpenCV）。

    OpenCV 的 VideoCapture 只接受文件路径，因此这里落地一个临时文件再读取，
    读完立即清理。
    """
    import tempfile
    from pathlib import Path

    import cv2

    path = Path(tempfile.mkdtemp(prefix="wenlv-poster-")) / "cover.mp4"
    path.write_bytes(data)
    try:
        capture = cv2.VideoCapture(str(path))
        try:
            ok, frame = capture.read()
        finally:
            capture.release()
        if not ok or frame is None:
            return None
        return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    finally:
        path.unlink(missing_ok=True)
        path.parent.rmdir()


class ShareService:
    def __init__(self) -> None:
        self.settings = get_settings()

    # ------------------------------------------------------------------
    def create(self, request: Any) -> dict[str, Any]:
        asset_id = getattr(request, "asset_id", None)
        plan_id = getattr(request, "plan_id", None)
        channel = getattr(request, "channel", "link") or "link"
        title = (getattr(request, "title", "") or "").strip()
        summary = (getattr(request, "summary", "") or "").strip()
        text = (getattr(request, "text", "") or "").strip()

        asset: CreationAsset | None = None
        plan: ItineraryPlan | None = None
        with SessionLocal() as db:
            if asset_id:
                asset = db.get(CreationAsset, asset_id)
                if asset is None:
                    raise LookupError("未找到对应的生成内容")
                title = title or asset.title
                summary = summary or (asset.text_content or "")[:160]
            if plan_id:
                plan = db.get(ItineraryPlan, plan_id)
                if plan is None:
                    raise LookupError("未找到对应的行程")
                title = title or plan.title
                summary = summary or plan.raw[:160]

        if not (asset or plan) and not (title or text):
            raise ValueError("请提供要分享的生成内容（asset_id / plan_id）或标题与正文")

        check_text(title, summary, text)

        poster_uri: str | None = None
        try:
            poster = self._poster(asset, title, summary or text, plan)
            poster_uri = store_bytes(poster, "image", "jpg", content_type="image/jpeg")
        except Exception as exc:  # 海报失败不应阻断分享
            logger.warning("分享海报合成失败，仅返回链接：%s", exc)

        token = secrets.token_urlsafe(12).replace("-", "").replace("_", "")[:20]
        expires = datetime.now(timezone.utc) + timedelta(seconds=self.settings.share_ttl_seconds)
        url = f"{self.settings.share_base_url.rstrip('/')}/?share={token}"

        with SessionLocal() as db:
            row = ShareLink(
                token=token,
                asset_id=asset.id if asset else None,
                channel=channel,
                title=title,
                summary=summary or text,
                url=url,
                poster_uri=poster_uri,
                expires_at=expires,
            )
            db.add(row)
            db.commit()
            share_id = row.id

        return {
            "token": token,
            "share_id": share_id,
            "url": url,
            "title": title,
            "summary": summary or text,
            "poster_uri": poster_uri,
            "poster_url": f"{self.settings.api_prefix}/share/{token}/poster" if poster_uri else None,
            "expires_in": self.settings.share_ttl_seconds,
        }

    # ------------------------------------------------------------------
    def resolve(self, token: str) -> dict[str, Any]:
        """按 token 取分享内容（供分享落地页渲染）。"""
        from sqlalchemy import select

        with SessionLocal() as db:
            link = db.scalars(select(ShareLink).where(ShareLink.token == token)).first()
            if link is None:
                raise LookupError("分享链接不存在或已失效")
            if link.expires_at and link.expires_at < datetime.now(timezone.utc):
                raise LookupError("分享链接已过期")
            link.visits = (link.visits or 0) + 1
            asset = db.get(CreationAsset, link.asset_id) if link.asset_id else None
            db.commit()

            payload: dict[str, Any] = {
                "token": token,
                "title": link.title,
                "summary": link.summary,
                "channel": link.channel,
                "visits": link.visits,
                "poster_url": f"{self.settings.api_prefix}/share/{token}/poster" if link.poster_uri else None,
                "asset": None,
            }
            if asset is not None:
                payload["asset"] = {
                    "id": asset.id,
                    "kind": asset.kind,
                    "title": asset.title,
                    "url": asset_file_url(asset.id),
                    "mime": asset.result_mime,
                    "text_content": asset.text_content,
                }
            return payload

    def poster_bytes(self, token: str) -> bytes:
        from sqlalchemy import select

        with SessionLocal() as db:
            link = db.scalars(select(ShareLink).where(ShareLink.token == token)).first()
            if link is None or not link.poster_uri:
                raise LookupError("分享海报不存在")
            return read_uri(link.poster_uri)

    # ------------------------------------------------------------------
    def _poster(self, asset: CreationAsset | None, title: str, note: str, plan: ItineraryPlan | None) -> bytes:
        """分享海报：以产物为视觉主体，叠加标题与来源标识。"""
        from ..providers.video import load_font

        width, height = 1080, 1440
        canvas = Image.new("RGB", (width, height), (251, 243, 231))
        draw = ImageDraw.Draw(canvas)

        visual_top, visual_h = 0, int(height * 0.68)
        visual = self._visual(asset)
        if visual is not None:
            ratio = visual_h / visual.height
            visual = visual.resize((int(visual.width * ratio), visual_h), Image.LANCZOS)
            left = (width - visual.width) // 2
            canvas.paste(visual.crop((0, 0, min(visual.width, width), visual_h)), (max(0, left), visual_top))
        else:
            # 文本类内容没有画面，用暖色块 + 摘要做视觉主体
            draw.rectangle([0, visual_top, width, visual_h], fill=(247, 226, 197))
            body_font = load_font(38)
            y = int(visual_h * 0.22)
            for line in self._wrap(draw, note or title, body_font, int(width * 0.82))[:12]:
                draw.text(((width - draw.textlength(line, font=body_font)) / 2, y), line, font=body_font, fill=(58, 44, 36))
                y += 56

        # 底部信息带
        draw.rectangle([0, visual_h, width, height], fill=(251, 243, 231))
        title_font = load_font(52)
        note_font = load_font(30)
        tag_font = load_font(26)

        draw.text((64, visual_h + 70), self._clip(draw, title, title_font, width - 128), font=title_font, fill=(58, 44, 36))

        meta = []
        if asset is not None:
            meta.append(f"类型：{asset.kind}")
        if plan is not None:
            meta.append(f"行程：{plan.duration}·{plan.theme}")
        meta.append(datetime.now().strftime("%Y-%m-%d"))
        draw.text((64, visual_h + 150), "　".join(meta), font=note_font, fill=(150, 120, 96))

        for index, line in enumerate(self._wrap(draw, note, note_font, width - 128)[:3]):
            draw.text((64, visual_h + 210 + index * 46), line, font=note_font, fill=(120, 96, 76))

        draw.line([(64, height - 130), (width - 64, height - 130)], fill=(228, 210, 186), width=2)
        draw.text((64, height - 106), "文旅创新智脑 · 扫码或打开链接查看完整内容", font=tag_font, fill=(150, 120, 96))

        buffer = BytesIO()
        canvas.save(buffer, format="JPEG", quality=92)
        return buffer.getvalue()

    @staticmethod
    def _visual(asset: CreationAsset | None) -> Image.Image | None:
        """取产物画面：图片直接用；视频用 OpenCV 抽首帧；文本类返回 None。"""
        if asset is None or not asset.result_uri:
            return None
        try:
            data = read_uri(asset.result_uri)
            mime = asset.result_mime or ""
            if mime.startswith("video"):
                return _video_first_frame(data)
            if not mime.startswith("image"):
                return None
            return Image.open(BytesIO(data)).convert("RGB")
        except Exception as exc:
            logger.warning("分享海报取图失败：%s", exc)
            return None

    @staticmethod
    def _wrap(draw: ImageDraw.ImageDraw, text: str, font, limit: int) -> list[str]:
        lines: list[str] = []
        current = ""
        for char in text.replace("\n", " "):
            probe = current + char
            if draw.textlength(probe, font=font) > limit and current:
                lines.append(current)
                current = char
            else:
                current = probe
        if current:
            lines.append(current)
        return lines or [""]

    @staticmethod
    def _clip(draw: ImageDraw.ImageDraw, text: str, font, limit: int) -> str:
        """标题超宽时截断加省略号，避免溢出画布。"""
        if draw.textlength(text, font=font) <= limit:
            return text
        while text and draw.textlength(text + "…", font=font) > limit:
            text = text[:-1]
        return text + "…"
