"""工单19 · 视频合成能力（FFmpeg + OpenCV）

工单编号：人工智能CV-AIGC-19-文旅Agent任务工单-创意策划与内容生成
对应 docs/01 §4.7：视频合成主选 **FFmpeg + OpenCV**。

设计取舍（工单19 §九「视频生成成熟度」风险提示要求以「照片合成 + 模板」为主）：
  - 不做文生视频，而是把游客上传的照片做**确定性的工程合成**：
    画面归一 → 字幕/水印 → 运镜（Ken Burns）→ 交叉淡入 → 配乐/解说音轨。
    这条链路不依赖外部模型，离线可稳定复现，符合工单对该风险的处置建议。
  - 字幕不用 ffmpeg 的 drawtext（Windows 下 fontfile 转义易出错、中文支持不稳），
    改为用 Pillow 预渲染成透明 PNG 再 overlay —— 字体可控、样式可设计、无转义问题。
  - 运镜在 1.4 倍画布上进行，缩放到 1.15 倍时窗口仍大于输出尺寸，不会像素化。
"""
from __future__ import annotations

import io
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Sequence

from PIL import Image, ImageDraw, ImageFont

from .base import VideoComposer

logger = logging.getLogger("wenlv.video")

# 画布相对输出尺寸的放大倍数：为运镜预留裁切余量
CANVAS_SCALE = 1.4
FPS = 25
FONT_CANDIDATES = (
    r"C:/Windows/Fonts/msyhbd.ttc",
    r"C:/Windows/Fonts/msyh.ttc",
    r"C:/Windows/Fonts/simhei.ttf",
)


def load_font(size: int) -> ImageFont.FreeTypeFont:
    """加载中文字体；全部缺失时退回 Pillow 默认字体（不阻断流程）。"""
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:  # 字体文件损坏时继续尝试下一个
                continue
    return ImageFont.load_default()


class FFmpegVideoComposer(VideoComposer):
    """把一组照片合成为带运镜、字幕与音轨的短片。"""

    name = "ffmpeg"

    def __init__(self, ffmpeg_bin: str = "ffmpeg", transition: float = 0.6) -> None:
        self.ffmpeg_bin = ffmpeg_bin
        self.transition = transition

    # ---------------- 环境 ----------------
    def _binary(self) -> str:
        found = shutil.which(self.ffmpeg_bin) or shutil.which("ffmpeg")
        if not found:
            raise RuntimeError(
                f"未找到 ffmpeg（配置值 {self.ffmpeg_bin}），视频合成不可用。"
                "请安装 FFmpeg 并加入 PATH（本机位于 C:/ffmpeg/bin）。"
            )
        return found

    # ---------------- 画面准备 ----------------
    @staticmethod
    def _normalize(raw: bytes, width: int, height: int) -> Image.Image:
        """等比缩放并居中裁切到目标尺寸（cover），避免画面被拉伸变形。"""
        image = Image.open(io.BytesIO(raw)).convert("RGB")
        target = width / height
        current = image.width / image.height
        if current > target:  # 过宽 → 以高为准裁两侧
            new_h = height
            new_w = max(width, int(round(new_h * current)))
        else:  # 过高 → 以宽为准裁上下
            new_w = width
            new_h = max(height, int(round(new_w / current)))
        image = image.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - width) // 2
        top = (new_h - height) // 2
        return image.crop((left, top, left + width, top + height))

    @staticmethod
    def _caption_layer(text: str, width: int, height: int) -> Image.Image:
        """把字幕预渲染为透明 PNG（底部居中、半透明底条），供 ffmpeg overlay 使用。"""
        layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        if not text:
            return layer
        draw = ImageDraw.Draw(layer)
        font = load_font(max(20, int(height * 0.042)))
        # 按像素宽度折行，中英文混排也能正确换行
        limit = int(width * 0.86)
        lines: list[str] = []
        current = ""
        for char in text:
            probe = current + char
            if draw.textlength(probe, font=font) > limit and current:
                lines.append(current)
                current = char
            else:
                current = probe
        if current:
            lines.append(current)
        lines = lines[:2]

        line_h = int(font.size * 1.45) if hasattr(font, "size") else 30
        block_h = line_h * len(lines)
        bar_h = block_h + int(height * 0.045)
        bar_y = height - bar_h - int(height * 0.04)
        draw.rounded_rectangle(
            [int(width * 0.06), bar_y, int(width * 0.94), bar_y + bar_h],
            radius=int(bar_h * 0.28),
            fill=(28, 18, 12, 150),
        )
        for index, line in enumerate(lines):
            text_w = draw.textlength(line, font=font)
            draw.text(
                ((width - text_w) / 2, bar_y + int(height * 0.022) + index * line_h),
                line,
                font=font,
                fill=(255, 246, 233, 255),
            )
        return layer

    def _watermark(self, image: Image.Image, text: str) -> None:
        """右下角署名水印，就地绘制。"""
        if not text:
            return
        draw = ImageDraw.Draw(image)
        font = load_font(max(16, int(image.height * 0.026)))
        text_w = draw.textlength(text, font=font)
        x = image.width - text_w - int(image.width * 0.035)
        y = int(image.height * 0.035)
        draw.text((x + 1, y + 1), text, font=font, fill=(0, 0, 0, 120))
        draw.text((x, y), text, font=font, fill=(255, 246, 233, 220))

    # ---------------- 合成 ----------------
    def compose(
        self,
        images: Sequence[bytes],
        seconds_per_image: float = 2.6,
        captions: Sequence[str] | None = None,
        audio: bytes | None = None,
        width: int = 1280,
        height: int = 720,
        watermark: str = "",
    ) -> bytes:
        if not images:
            raise ValueError("视频合成至少需要一张图片")

        seconds = max(1.2, float(seconds_per_image))
        frames = max(int(FPS * seconds), int(FPS * 1.2))
        transition = min(self.transition, seconds * 0.4)
        canvas_w, canvas_h = int(width * CANVAS_SCALE), int(height * CANVAS_SCALE)

        with tempfile.TemporaryDirectory(prefix="wenlv-video-") as workdir:
            root = Path(workdir)
            command: list[str] = [self._binary(), "-y", "-hide_banner", "-loglevel", "error"]
            filters: list[str] = []
            clip_labels: list[str] = []

            for index, raw in enumerate(images):
                # 运镜画布：比输出更大，为平移/缩放留余量
                frame = self._normalize(raw, canvas_w, canvas_h)
                self._watermark(frame, watermark)
                frame_path = root / f"frame{index:02d}.png"
                frame.save(frame_path, format="PNG")

                caption_path = root / f"caption{index:02d}.png"
                caption_text = captions[index] if captions and index < len(captions) else ""
                self._caption_layer(caption_text, width, height).save(caption_path, format="PNG")

                command += ["-i", str(frame_path)]

            for index in range(len(images)):
                caption_path = root / f"caption{index:02d}.png"
                command += ["-i", str(caption_path)]

            for index in range(len(images)):
                # 交替「推近 / 拉远」，避免每段运镜方向一致显得单调
                if index % 2 == 0:
                    zoom = "min(zoom+0.0011,1.15)"
                else:
                    zoom = "if(lte(zoom,1.0),1.15,max(1.001,zoom-0.0011))"
                filters.append(
                    f"[{index}:v]scale={canvas_w}:{canvas_h}:force_original_aspect_ratio=increase,"
                    f"crop={canvas_w}:{canvas_h},"
                    f"zoompan=z='{zoom}':d={frames}"
                    f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                    f":s={width}x{height}:fps={FPS},setsar=1[base{index}]"
                )
                # 字幕用透明层叠加，因此不参与运镜，始终保持清晰、位置固定
                filters.append(
                    f"[base{index}][{len(images) + index}:v]overlay=0:0:format=auto[c{index}]"
                )
                clip_labels.append(f"[c{index}]")

            if len(images) == 1:
                video_label = clip_labels[0]
            else:
                # 交叉淡入：xfade 的 offset 相对第一路时间轴，第 k 次叠加偏移 k*(D-T)
                step = seconds - transition
                previous = clip_labels[0]
                for index in range(1, len(images)):
                    offset = step * index
                    out = f"[x{index}]"
                    filters.append(
                        f"{previous}{clip_labels[index]}xfade=transition=fade"
                        f":duration={transition:.3f}:offset={offset:.3f}{out}"
                    )
                    previous = out
                video_label = previous

            command += ["-filter_complex", ";".join(filters), "-map", video_label]

            if audio:
                audio_path = root / "bgm.mp3"
                audio_path.write_bytes(audio)
                audio_index = len(images) * 2
                command += ["-i", str(audio_path), "-map", f"{audio_index}:a", "-shortest", "-c:a", "aac", "-b:a", "128k"]

            output_path = root / "output.mp4"
            command += [
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-crf", "20",
                "-preset", "veryfast",
                "-movflags", "+faststart",
                "-r", str(FPS),
                str(output_path),
            ]
            logger.info("合成旅行短片：%d 张图 · %d 帧/段 · 总时长约 %.1fs", len(images), frames, seconds * len(images))
            result = subprocess.run(command, capture_output=True, text=True, timeout=600)
            if result.returncode != 0 or not output_path.exists():
                raise RuntimeError(f"ffmpeg 合成失败：{result.stderr.strip()[:400]}")
            return output_path.read_bytes()

    # ---------------- 帧抽取（供封面/分享海报复用） ----------------
    @staticmethod
    def first_frame(video: bytes) -> bytes:
        """用 OpenCV 取首帧作为视频封面（docs/01 指定的 FFmpeg + OpenCV 组合）。"""
        import cv2
        import numpy as np

        array = cv2.imdecode(np.frombuffer(video, dtype=np.uint8), cv2.IMREAD_COLOR)
        if array is None:
            raise ValueError("无法解析视频数据")
        return bytes(cv2.imencode(".jpg", array)[1].tobytes())


def probe_video(video: bytes) -> dict[str, Any]:
    """用 OpenCV 读取时长/分辨率/帧数，用于接口回显与验收核对。"""
    import cv2
    import numpy as np

    path = Path(tempfile.mkdtemp(prefix="wenlv-probe-")) / "p.mp4"
    path.write_bytes(video)
    capture = cv2.VideoCapture(str(path))
    try:
        fps = capture.get(cv2.CAP_PROP_FPS) or 0.0
        count = capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
        return {
            "width": int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "fps": round(fps, 2),
            "frames": int(count),
            "duration_seconds": round(count / fps, 2) if fps else 0.0,
        }
    finally:
        capture.release()
        shutil.rmtree(path.parent, ignore_errors=True)
