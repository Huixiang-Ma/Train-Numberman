"""工单19 · 专属纪念内容自动生成

工单编号：人工智能CV-AIGC-19-文旅Agent任务工单-创意策划与内容生成
对应 docs/05 §3.2 / §4.2：
  - 照片 → 艺术风格化纪念照、明信片、虚拟合影（图像生成 + 风格迁移）
  - 照片/视频 → 短视频、电子相册、旅行日记（FFmpeg 合成 + LLM 文案）

实现取舍：
  - **风格迁移走 image-edit（图生图）而不是文生图**：纪念照必须保留游客本人的面容与
    构图，纯文生图会"换一个人"。实测该模型单图输入可用（多图输入返回 400），
    因此虚拟合影采用「AI 生成场景 + 抠出游客人像合成」的确定性组合。
  - **短视频=照片合成**，不做文生视频（docs/05 §九 已提示文生视频成熟度风险）。
"""
from __future__ import annotations

import io
import logging
from datetime import datetime
from typing import Any, Sequence

from PIL import Image, ImageDraw

from ..core.config import get_settings
from ..db.base import SessionLocal
from ..db.models import CreationAsset
from ..providers.registry import get_image, get_llm, get_tts, get_video
from .creative_common import check_text, extract_json, read_uri, store_bytes

logger = logging.getLogger("wenlv.creation")

# 风格预设：每个风格给「画面风格描述」与「后处理色调」，保证观感与文案一致
STYLE_PRESETS: dict[str, dict[str, str]] = {
    "ink": {"name": "水墨写意", "prompt": "中国水墨画风格，宣纸质感，墨色浓淡相宜，大量留白，写意笔触"},
    "gongbi": {"name": "工笔重彩", "prompt": "中国传统工笔画风格，线条工整细腻，矿物颜料重彩，典雅华丽"},
    "oil": {"name": "古典油画", "prompt": "欧洲古典油画风格，厚涂笔触，温暖侧光，伦勃朗式明暗层次"},
    "film": {"name": "复古胶片", "prompt": "上世纪八十年代彩色胶片摄影风格，颗粒感，暖黄褪色调，怀旧氛围"},
    "anime": {"name": "新海诚动画", "prompt": "日式动画电影风格，澄澈天空，细腻光影，青蓝与暖橙对比色调"},
    "tang": {"name": "唐风重彩", "prompt": "唐代壁画重彩风格，赭石与石青配色，古朴庄重，敦煌飞天韵味"},
}
DEFAULT_STYLE = "ink"

DIARY_SYSTEM = (
    "你是《文旅创新智脑》的旅行记录编辑。依据给定行程要素写一篇旅行日记，"
    "语言温暖真挚，避免空洞抒情与夸张修辞，控制在 400 字以内，只用简体中文。"
    "输出必须是**一个 JSON 对象**："
    '{"title": "日记标题", "body": "日记正文", "highlights": ["亮点1", "亮点2"]}'
)
NARRATION_SYSTEM = (
    "你是旅行短片的解说词撰稿人。依据给定要素写一段 80 字以内的解说词，"
    "语气舒缓、画面感强，只用简体中文，只输出解说词正文。"
)


class CreationService:
    def __init__(self) -> None:
        self.settings = get_settings()

    # ------------------------------------------------------------------
    # 图像类
    # ------------------------------------------------------------------
    def artistic(self, image: bytes, style: str = DEFAULT_STYLE, title: str = "") -> dict[str, Any]:
        """艺术风格化纪念照：图生图，保留人物与构图，只换画风。"""
        preset = STYLE_PRESETS.get(style) or STYLE_PRESETS[DEFAULT_STYLE]
        prompt = (
            f"以这张旅行照片为基础进行艺术化处理：{preset['prompt']}。"
            "严格保留原照片中的人物相貌、姿势、人数与画面构图，不要添加或删除人物，"
            "不要改变场景内容，只改变绘画风格与色调。"
        )
        check_text(prompt)
        result = get_image().edit_image(image, prompt)
        name = title or f"{preset['name']}纪念照"
        return self._persist_image("artistic", name, result, prompt, {"style": style}, ["纪念照", preset["name"]])

    def postcard(
        self,
        image: bytes,
        text: str = "",
        place: str = "",
        title: str = "",
        style: str = DEFAULT_STYLE,
    ) -> dict[str, Any]:
        """明信片：先做风格化，再套上可邮寄的明信片版式（边框 / 标题 / 地点 / 日期 / 印章）。"""
        preset = STYLE_PRESETS.get(style) or STYLE_PRESETS[DEFAULT_STYLE]
        prompt = (
            f"把这章旅行照片处理成{preset['name']}风格的明信片主图：{preset['prompt']}。"
            "保留人物相貌与主要景物，构图舒展，画面适合作为明信片封面。"
        )
        check_text(prompt, text)
        styled = get_image().edit_image(image, prompt)
        framed = self._postcard_frame(styled, title=title or "旅行纪念明信片", place=place, text=text)
        return self._persist_image(
            "postcard", title or "旅行纪念明信片", framed, prompt, {"style": style, "place": place, "text": text}, ["明信片"]
        )

    def group_photo(self, images: Sequence[bytes], scene: str = "", title: str = "") -> dict[str, Any]:
        """虚拟合影：AI 生成场景底图 + 抠出游客人像合成。

        该模型（Qwen-Image-Edit）的 image 参数只接受单张图（多图返回 400），
        因此无法让模型直接"把两张照片里的人合成到一起"，改为确定性组合：
        文生图出场景 → YOLO+SAM 2 抠人 → 按人数横向分布贴图 → 统一色调。
        """
        if not images:
            raise ValueError("虚拟合影至少需要一张照片")
        scene_text = scene or "中国古典园林中的庭院，飞檐回廊，暖阳斜照，适合拍摄纪念合影"
        background_prompt = f"{scene_text}，空无一人，前景留出站立位置，高清摄影"
        check_text(background_prompt)
        background = Image.open(io.BytesIO(get_image().generate_image(background_prompt, size="1024x1024"))).convert("RGB")

        cutouts: list[Image.Image] = []
        segmented = 0
        try:
            from ..providers.registry import get_segmenter

            segmenter = get_segmenter()
            for raw in images[:4]:
                png = segmenter.cutout_person(raw)  # type: ignore[attr-defined]
                if png:
                    cutouts.append(Image.open(io.BytesIO(png)).convert("RGBA"))
                    segmented += 1
        except Exception as exc:
            logger.warning("人像抠取失败，退化为仅输出场景底图：%s", exc)

        if cutouts:
            composed = self._compose_group(background, cutouts)
        else:
            # 抠人失败时不伪造"合影"，而是给出场景底图 + 明确说明，便于前端如实提示
            composed = background

        name = title or "虚拟合影"
        asset = self._persist_image(
            "group_photo",
            name,
            self._encode(composed, "JPEG", quality=92),
            background_prompt,
            {"scene": scene_text, "persons_segmented": segmented, "persons_input": len(images)},
            ["虚拟合影"],
            ext="jpg",
            mime="image/jpeg",
        )
        asset["extra"]["persons_segmented"] = segmented
        asset["extra"]["degraded"] = segmented == 0
        return asset

    # ------------------------------------------------------------------
    # 视频类
    # ------------------------------------------------------------------
    def video(
        self,
        images: Sequence[bytes],
        title: str = "我的旅行回忆",
        captions: Sequence[str] | None = None,
        seconds_per_image: float | None = None,
        watermark: str = "文旅创新智脑",
        with_narration: bool = False,
    ) -> dict[str, Any]:
        """电子相册 / 旅行短片：FFmpeg 运镜 + 交叉淡入 + 字幕 + 可选解说音轨。"""
        if not images:
            raise ValueError("视频合成至少需要一张照片")
        limit = self.settings.video_max_images
        images = list(images)[:limit]

        captions = [str(c)[:80] for c in (captions or [])][: len(images)]
        seconds = float(seconds_per_image or self.settings.video_seconds_per_image)

        audio: bytes | None = None
        narration = ""
        if with_narration:
            narration = self._narration(title, captions)
            if narration:
                try:
                    audio = self._speech(narration)
                except Exception as exc:  # 配音失败不阻断成片
                    logger.warning("解说音轨合成失败，改为纯音乐/无声：%s", exc)

        check_text(title, " ".join(captions), narration)
        composed = get_video().compose(
            images,
            seconds_per_image=seconds,
            captions=captions,
            audio=audio,
            width=self.settings.video_width,
            height=self.settings.video_height,
            watermark=watermark,
        )

        from ..providers.video import probe_video

        meta = probe_video(composed)
        uri = store_bytes(composed, "video", "mp4", content_type="video/mp4")
        asset = self._persist_asset(
            kind="video",
            title=title,
            uri=uri,
            mime="video/mp4",
            size=len(composed),
            text=narration,
            prompt="　".join(captions),
            params={"images": len(images), "seconds_per_image": seconds, "with_narration": bool(audio), **meta},
            tags=["短视频"],
        )
        asset["extra"].update(meta)
        asset["extra"]["has_audio"] = bool(audio)
        return asset

    # ------------------------------------------------------------------
    # 文本类
    # ------------------------------------------------------------------
    def diary(
        self,
        image_count: int = 0,
        title: str = "我的旅行日记",
        tone: str = "温暖记录",
        place: str = "",
        highlights: Sequence[str] | None = None,
        captions: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        """旅行日记：把行程要素交给 LLM 成文，失败时用确定性模板兜底。"""
        highlights = [str(h) for h in (highlights or []) if str(h).strip()]
        captions = [str(c) for c in (captions or []) if str(c).strip()]
        check_text(title, " ".join(highlights + captions))

        body = ""
        picked = highlights
        model = "fallback:template"
        try:
            prompt = (
                f"【标题】{title}\n【地点】{place or '景区'}\n【语气】{tone}\n"
                f"【照片数量】{image_count} 张\n"
                f"【当日亮点】{'、'.join(highlights) or '未特别说明'}\n"
                f"【照片配文】{' / '.join(captions) or '无'}\n"
                "请写一篇旅行日记。" 
            )
            raw = get_llm().generate(prompt, system=DIARY_SYSTEM)
            check_text(raw)
            parsed = extract_json(raw)
            if isinstance(parsed, dict) and parsed.get("body"):
                title = str(parsed.get("title") or title)[:200]
                body = str(parsed["body"])[:2000]
                picked = [str(x)[:80] for x in (parsed.get("highlights") or []) if str(x).strip()] or highlights
                model = self.settings.sf_llm_model
        except Exception as exc:
            logger.warning("旅行日记生成失败，转模板兜底：%s", exc)

        if not body:
            body = self._fallback_diary(title, place, tone, image_count, picked or captions)
            picked = picked or captions

        uri = store_bytes(body.encode("utf-8"), "text", "txt", content_type="text/plain; charset=utf-8")
        asset = self._persist_asset(
            kind="diary",
            title=title,
            uri=uri,
            mime="text/plain; charset=utf-8",
            size=len(body.encode("utf-8")),
            text=body,
            prompt=f"{tone}／{place}",
            params={"image_count": image_count, "highlights": picked, "tone": tone},
            tags=["旅行日记"],
            model=model,
        )
        asset["extra"]["highlights"] = picked
        return asset

    @staticmethod
    def _fallback_diary(title: str, place: str, tone: str, count: int, points: Sequence[str]) -> str:
        where = place or "景区"
        lines = [f"{title}", "", f"今天的行程在{where}，一共留下 {count} 张照片。"]
        if points:
            lines.append("印象最深的几处：")
            lines.extend(f"· {p}" for p in points[:5])
        lines.append("")
        lines.append("把照片和这些片段放在一起，就是这一天完整的记忆。")
        lines.append(f"（{tone}）")
        return "\n".join(lines)

    def _narration(self, title: str, captions: Sequence[str]) -> str:
        try:
            prompt = f"【短片标题】{title}\n【画面配文】{' / '.join(captions) or '无'}\n请写解说词。"
            text = get_llm().generate(prompt, system=NARRATION_SYSTEM).strip()
            check_text(text)
            return text[:160]
        except Exception as exc:
            logger.warning("解说词生成失败：%s", exc)
            return ""

    @staticmethod
    def _speech(text: str) -> bytes:
        """CosyVoice 合成解说音轨（base64 mp3 → bytes）。"""
        import base64

        payload = get_tts().synthesize(text, lang="zh")
        return base64.b64decode(payload["audio_base64"])

    # ------------------------------------------------------------------
    # 导览地图（工单20 场景13）
    # ------------------------------------------------------------------
    def guide_map(self, stops: Sequence[dict], title: str = "个性化导览地图", subtitle: str = "") -> dict[str, Any]:
        """按行程分站生成可下载打印的导览地图。

        坐标取自 **PostGIS 里的真实景点/活动数据**，而不是让模型"画一张图"：
        地图必须与实际位置一致才有导览价值，坐标错位的地图比没有地图更糟。
        分站名称匹配不到坐标时如实记录在 params.skipped 中，不臆造位置。
        """
        from sqlalchemy import func, select

        from ..db.models import Activity, Attraction
        from ..providers.map import SiteMapRenderer

        with SessionLocal() as db:
            rows = db.execute(
                select(
                    Attraction.name,
                    func.ST_X(Attraction.geom),
                    func.ST_Y(Attraction.geom),
                ).where(Attraction.geom.isnot(None))
            ).all()
            all_points = [{"name": name, "lon": float(lon), "lat": float(lat)} for name, lon, lat in rows]
            coords = {item["name"]: (item["lon"], item["lat"]) for item in all_points}

            for name, lon, lat in db.execute(
                select(Activity.name, func.ST_X(Activity.geom), func.ST_Y(Activity.geom)).where(Activity.geom.isnot(None))
            ).all():
                coords.setdefault(name, (float(lon), float(lat)))

        plotted: list[dict[str, Any]] = []
        skipped: list[str] = []
        for order, stop in enumerate(stops, start=1):
            name = str(stop.get("name") or "").strip()
            point = coords.get(name)
            if point is None:
                skipped.append(name)
                continue
            plotted.append({"name": name, "lon": point[0], "lat": point[1], "index": order})

        if not plotted:
            raise ValueError("行程中的分站均无坐标数据，无法绘制导览地图")

        png = SiteMapRenderer().render(title, plotted, all_points=all_points, subtitle=subtitle)
        asset = self._persist_image(
            "map",
            title,
            png,
            f"导览地图：{title}",
            {"stops": len(plotted), "skipped": skipped, "all_points": len(all_points)},
            ["导览地图"],
        )
        asset["extra"]["plotted"] = [item["name"] for item in plotted]
        asset["extra"]["skipped"] = skipped
        return asset

    # ------------------------------------------------------------------
    # 活动回顾 PPT（工单20 场景12 · docs/01 §4.7 python-pptx）
    # ------------------------------------------------------------------
    def review_ppt(
        self,
        images: Sequence[bytes],
        title: str = "活动回顾",
        notes: Sequence[str] | None = None,
        subtitle: str = "",
    ) -> dict[str, Any]:
        """把活动照片整理成回顾 PPT（封面 + 每图一页 + 结尾页）。"""
        from pptx import Presentation
        from pptx.dml.color import RGBColor
        from pptx.util import Emu, Inches, Pt

        if not images:
            raise ValueError("生成回顾 PPT 至少需要一张照片")

        notes = [str(n) for n in (notes or [])]
        deck = Presentation()
        deck.slide_width = Inches(13.333)  # 16:9
        deck.slide_height = Inches(7.5)
        blank = deck.slide_layouts[6]

        def add_text(slide, text: str, left, top, width, height, size: int, bold: bool = False, color=(58, 44, 36)):
            box = slide.shapes.add_textbox(left, top, width, height)
            frame = box.text_frame
            frame.text = text
            paragraph = frame.paragraphs[0]
            paragraph.font.size = Pt(size)
            paragraph.font.bold = bold
            paragraph.font.color.rgb = RGBColor(*color)
            return box

        # 封面
        cover = deck.slides.add_slide(blank)
        cover.background.fill.solid()
        cover.background.fill.fore_color.rgb = RGBColor(251, 243, 231)
        add_text(cover, title, Inches(1.0), Inches(2.6), Inches(11.3), Inches(1.6), 44, bold=True)
        if subtitle:
            add_text(cover, subtitle, Inches(1.0), Inches(4.2), Inches(11.3), Inches(0.8), 20, color=(150, 96, 36))

        # 每张照片一页：等比缩放居中，避免拉伸变形
        for index, raw in enumerate(images):
            slide = deck.slides.add_slide(blank)
            photo = Image.open(io.BytesIO(raw))
            # 版心：宽 11.3"、高 5.0"，按图片宽高比取较小缩放
            max_w, max_h = 11.3, 5.0
            ratio = min(max_w / photo.width, max_h / photo.height)
            width = Emu(int(Inches(1) * ratio * photo.width))
            height = Emu(int(Inches(1) * ratio * photo.height))
            left = Emu(int((deck.slide_width - width) / 2))
            slide.shapes.add_picture(io.BytesIO(raw), left, Inches(1.35), width=width, height=height)
            caption = notes[index] if index < len(notes) and notes[index] else f"{title} · {index + 1}"
            add_text(slide, caption, Inches(1.0), Inches(6.5), Inches(11.3), Inches(0.7), 18)

        # 结尾页
        end = deck.slides.add_slide(blank)
        add_text(end, "感谢参与 · 由《文旅创新智脑》自动整理", Inches(1.0), Inches(3.2), Inches(11.3), Inches(1.0), 26)

        buffer = io.BytesIO()
        deck.save(buffer)
        data = buffer.getvalue()

        uri = store_bytes(data, "text", "pptx",
                          content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation")
        asset = self._persist_asset(
            kind="review_ppt",
            title=title,
            uri=uri,
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            size=len(data),
            text="",
            prompt="活动回顾 PPT",
            params={"slides": len(images) + 2, "photos": len(images)},
            tags=["活动回顾", "PPT"],
            model="python-pptx",
        )
        asset["extra"]["slides"] = len(images) + 2
        return asset

    # ------------------------------------------------------------------
    # 版式与合成（Pillow）
    # ------------------------------------------------------------------
    def _postcard_frame(self, raw: bytes, title: str, place: str, text: str) -> bytes:
        """明信片版式：暖白卡纸边 + 底部题字 + 地点日期 + 朱印。"""
        from ..providers.video import load_font

        photo = Image.open(io.BytesIO(raw)).convert("RGB")
        width = max(900, photo.width)
        photo = photo.resize((width, int(photo.height * width / photo.width)), Image.LANCZOS)

        border = int(width * 0.035)
        band = int(width * 0.20)
        canvas = Image.new("RGB", (width + border * 2, photo.height + border + band), (251, 243, 231))
        canvas.paste(photo, (border, border))
        draw = ImageDraw.Draw(canvas)

        # 内描边，读起来像一张压印的卡纸
        draw.rectangle([border, border, border + width, border + photo.height], outline=(228, 210, 186), width=2)

        title_font = load_font(int(width * 0.036))
        meta_font = load_font(int(width * 0.022))
        text_y = border + photo.height + int(band * 0.18)
        draw.text((border + int(width * 0.01), text_y), title, font=title_font, fill=(58, 44, 36))

        subtitle = "　".join(x for x in (place, datetime.now().strftime("%Y-%m-%d")) if x)
        draw.text((border + int(width * 0.01), text_y + int(width * 0.046)), subtitle, font=meta_font, fill=(150, 120, 96))

        if text:
            note = text[:34]
            draw.text((border + int(width * 0.01), text_y + int(width * 0.078)), note, font=meta_font, fill=(120, 96, 76))

        # 朱印：右上角方形印章，纯图形绘制避免依赖外部位图
        seal = int(width * 0.075)
        sx, sy = border + width - seal - int(width * 0.02), text_y - int(seal * 0.15)
        draw.rounded_rectangle([sx, sy, sx + seal, sy + seal], radius=int(seal * 0.16), fill=(176, 74, 60))
        seal_font = load_font(int(seal * 0.42))
        draw.text((sx + seal * 0.16, sy + seal * 0.1), "游", font=seal_font, fill=(255, 240, 232))
        draw.text((sx + seal * 0.16, sy + seal * 0.5), "记", font=seal_font, fill=(255, 240, 232))

        return self._encode(canvas, "JPEG", quality=93)

    def _compose_group(self, background: Image.Image, cutouts: Sequence[Image.Image]) -> Image.Image:
        """把人像按人数横向分布贴到场景底图上，底部对齐、统一高度。"""
        canvas = background.copy()
        count = len(cutouts)
        target_h = int(canvas.height * (0.62 if count <= 2 else 0.52))
        slot_w = canvas.width / (count + 1)
        baseline = int(canvas.height * 0.92)

        for index, person in enumerate(cutouts):
            ratio = target_h / person.height
            person = person.resize((max(1, int(person.width * ratio)), target_h), Image.LANCZOS)
            cx = int(slot_w * (index + 1))
            left = max(0, min(canvas.width - person.width, cx - person.width // 2))
            canvas.paste(person, (left, baseline - person.height), person)
        return canvas

    @staticmethod
    def _encode(image: Image.Image, fmt: str, **kwargs: Any) -> bytes:
        buffer = io.BytesIO()
        image.save(buffer, format=fmt, **kwargs)
        return buffer.getvalue()

    # ------------------------------------------------------------------
    # 落库
    # ------------------------------------------------------------------
    def _persist_image(
        self,
        kind: str,
        title: str,
        data: bytes,
        prompt: str,
        params: dict,
        tags: list[str],
        ext: str = "png",
        mime: str = "image/png",
    ) -> dict[str, Any]:
        uri = store_bytes(data, "image", ext, content_type=mime)
        return self._persist_asset(
            kind=kind, title=title, uri=uri, mime=mime, size=len(data), text="", prompt=prompt, params=params, tags=tags
        )

    def _persist_asset(
        self,
        kind: str,
        title: str,
        uri: str,
        mime: str,
        size: int,
        text: str,
        prompt: str,
        params: dict,
        tags: list[str],
        model: str = "",
    ) -> dict[str, Any]:
        model = model or self.settings.sf_image_model
        asset_id: str | None = None
        try:
            with SessionLocal() as db:
                row = CreationAsset(
                    kind=kind,
                    title=title,
                    status="success",
                    result_uri=uri,
                    result_mime=mime,
                    size_bytes=size,
                    text_content=text,
                    prompt=prompt,
                    model=model,
                    params=params,
                    tags=tags,
                )
                db.add(row)
                db.commit()
                asset_id = row.id
        except Exception as exc:
            logger.warning("生成产物落库失败（不影响返回）：%s", exc)

        return {
            "id": asset_id or "",
            "kind": kind,
            "title": title,
            "status": "success",
            "result_uri": uri,
            "url": f"{self.settings.api_prefix}/create/asset/{asset_id}/file" if asset_id else None,
            "text_content": text,
            "mime": mime,
            "size_bytes": size,
            "prompt": prompt,
            "model": model,
            "extra": dict(params),
        }

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def list_assets(self, kind: str | None = None, limit: int = 20) -> dict[str, Any]:
        from sqlalchemy import func, select

        with SessionLocal() as db:
            stmt = select(CreationAsset)
            if kind:
                stmt = stmt.where(CreationAsset.kind == kind)
            rows = list(db.scalars(stmt.order_by(CreationAsset.created_at.desc()).limit(max(1, min(100, limit)))))
            total = db.scalar(select(func.count()).select_from(CreationAsset))
            items = [self.to_out(row) for row in rows]
        return {"items": items, "total": int(total or 0)}

    def get_asset(self, asset_id: str) -> CreationAsset | None:
        with SessionLocal() as db:
            return db.get(CreationAsset, asset_id)

    @staticmethod
    def to_out(row: CreationAsset) -> dict[str, Any]:
        from .creative_common import asset_file_url

        return {
            "id": row.id,
            "kind": row.kind,
            "title": row.title,
            "status": row.status,
            "result_uri": row.result_uri,
            "url": asset_file_url(row.id) if row.result_uri else None,
            "text_content": row.text_content or "",
            "mime": row.result_mime or "",
            "size_bytes": row.size_bytes or 0,
            "prompt": row.prompt or "",
            "model": row.model or "",
            "extra": row.params or {},
        }
