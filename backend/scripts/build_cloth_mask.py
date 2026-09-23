"""工单18 · 从青瓷全身素材派生「衣物微风」作用遮罩

工单编号：人工智能CV-AIGC-18-文旅Agent任务工单-智能导览与互动体验

为什么需要派生遮罩：
  现有形象是**单张全身透明 PNG**，没有独立衣物图层。数字人要有"衣摆/袖摆被风托起"
  的生命感，就必须知道"哪些像素属于衣物"。让模型重新出图会改动已验收的人物本体，
  因此这里用几何 + alpha 从原图派生一张灰度遮罩，运行时由 AvatarStage 的顶点着色器
  采样它来施加低幅度位移。

遮罩取值：
  0   = 不参与风感（头、脸、手、背景）
  255 = 完全参与（衣摆、袖摆主体）

排除手部是硬约束：手有独立骨骼与延迟跟随（腕手骨），若同一批顶点既被风推、
又被手骨拉，会互相抵消并在腕口撕裂。宁可衣袖少动一点，也不能让手漂移。

运行（幂等，可重复执行）：
  cd backend && python scripts/build_cloth_mask.py
  cd backend && python scripts/build_cloth_mask.py --id qingci-full
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AVATAR_DIR = ROOT / "frontend" / "public" / "avatar"

# 纵向权重：肩部以下开始出现衣料感，越往下（裙摆）越明显。
# 默认值按**半身像**构图标定；全身立绘的衣料起点更高、裙摆更长，
# 用 --upper/--lower 覆盖（例如 --upper 0.30 --lower 0.55）。
UPPER = 0.50  # 此高度以上完全不参与（头/颈/胸口以上）
LOWER = 0.72  # 此高度以下取满权重
# 手部排除：在 meta.hands 的并集外扩后做平滑衰减，外扩系数越大，手周围保留的衣料越多
HAND_PADDING = 0.06
HAND_FEATHER = 0.05
BLUR_RADIUS = 6.0


def _load_meta(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _hand_region(meta: dict) -> tuple[float, float, float, float] | None:
    """双手并集（归一化 x0, y0, x1, y1）；素材缺手部关键点时返回 None。"""
    boxes = [meta["hands"]["left"], meta["hands"]["right"]]
    boxes = [box for box in boxes if box]
    if not boxes:
        return None
    x0 = min(box["x"] for box in boxes) - HAND_PADDING
    y0 = min(box["y"] for box in boxes) - HAND_PADDING
    x1 = max(box["x"] + box["w"] for box in boxes) + HAND_PADDING
    y1 = max(box["y"] + box["h"] for box in boxes) + HAND_PADDING
    return max(0.0, x0), max(0.0, y0), min(1.0, x1), min(1.0, y1)


def build_mask(avatar_id: str = "qingci", upper: float = UPPER, lower: float = LOWER) -> Path:
    import numpy as np
    from PIL import Image, ImageFilter

    cutout = AVATAR_DIR / f"{avatar_id}-cutout.png"
    meta_path = AVATAR_DIR / f"{avatar_id}.json"
    output = AVATAR_DIR / f"{avatar_id}-cloth-mask.png"

    if not cutout.exists():
        raise SystemExit(f"缺少形象素材：{cutout}")

    meta = _load_meta(meta_path)
    image = Image.open(cutout).convert("RGBA")
    width, height = image.size

    alpha = np.asarray(image.split()[-1], dtype=np.float32) / 255.0
    rows = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]

    # 纵向权重：upper 以上为 0，lower 以下为 1，中间平滑过渡
    vertical = np.clip((rows - upper) / max(1e-6, lower - upper), 0.0, 1.0)
    vertical = vertical * vertical * (3.0 - 2.0 * vertical)

    weight = alpha * vertical

    hand = _hand_region(meta)
    if hand is not None:
        x0, y0, x1, y1 = hand
        cols = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :]
        # 手部区域内为 0，边界外 HAND_FEATHER 范围内平滑升到 1
        inside_x = np.clip((cols - x1) / HAND_FEATHER, 0.0, 1.0) + np.clip((x0 - cols) / HAND_FEATHER, 0.0, 1.0)
        inside_y = np.clip((rows - y1) / HAND_FEATHER, 0.0, 1.0) + np.clip((y0 - rows) / HAND_FEATHER, 0.0, 1.0)
        keep = np.clip(inside_x + inside_y, 0.0, 1.0)
        weight = weight * keep

    mask = Image.fromarray((np.clip(weight, 0.0, 1.0) * 255.0).astype(np.uint8), mode="L")
    mask = mask.filter(ImageFilter.GaussianBlur(BLUR_RADIUS))
    mask.save(output)

    active = int((np.asarray(mask) > 8).sum())
    ratio = active / float(width * height)
    print(f"尺寸 {width}x{height} · 模式 {mask.mode} · 有效像素 {active}（{ratio:.1%}）")
    if active == 0:
        raise SystemExit("遮罩为空，请检查素材与阈值")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="从形象素材派生衣物微风遮罩（工单18）")
    parser.add_argument("--id", default="qingci", help="数字人标识，用于定位素材与输出文件")
    parser.add_argument("--upper", type=float, default=UPPER, help="此归一化高度以上不参与风感")
    parser.add_argument("--lower", type=float, default=LOWER, help="此归一化高度以下取满权重")
    cli = parser.parse_args()
    result = build_mask(cli.id, upper=cli.upper, lower=cli.lower)
    print(f"已写出：{result}")
    sys.exit(0)
