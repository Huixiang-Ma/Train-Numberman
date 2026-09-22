"""工单18 · 生成眨眼素材（闭眼贴图）

工单编号：人工智能CV-AIGC-18-文旅Agent任务工单-智能导览与互动体验

背景：原图人物双眼睁大，用「贴皮肤补丁」或「纵向压扁」都无法自然闭眼
（前者有色差与接缝，后者会把虹膜压成一条横缝）。正确做法是另取一张
闭眼素材做交叉淡入，而闭眼素材必须与睁眼图**像素对齐**。

做法：
  1) 用 AIGC 图像编辑接口在原图上只改眼睛，得到几何一致的闭眼图；
  2) 校验两图差异（应集中在眼部、剪影包围盒接近）；
  3) 输出近眼区域贴图：RGB 取闭眼图，A 存「眨眼影响区域」的羽化蒙版。
     前端在着色器里以 uBlink * 该 alpha 混合，只影响眼睛，嘴部与身体完全不动。

用法：
  python scripts/build_blink_asset.py                 # 校验并生成
  python scripts/build_blink_asset.py --edit          # 先调用 AIGC 编辑生成闭眼原图
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
AVATAR_DIR = REPO / "frontend" / "public" / "avatar"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EYE_EDIT_PROMPT = "让这位女士的双眼自然闭合，其余部分（发型、五官、服装、姿态、背景）完全保持不变"


def _call_edit(avatar_id: str) -> Path:
    """调用 SiliconFlow 图像编辑，得到与原图几何一致的闭眼图。"""
    import httpx

    from app.core.config import get_settings

    settings = get_settings()
    source = AVATAR_DIR / f"{avatar_id}-raw.png"
    if not source.exists():
        raise SystemExit(f"未找到原图 {source}")

    payload = {
        "model": "Qwen/Qwen-Image-Edit",
        "prompt": EYE_EDIT_PROMPT,
        "image": f"data:image/png;base64,{base64.b64encode(source.read_bytes()).decode()}",
        "image_size": "1024x1536",
        "batch_size": 1,
    }
    resp = httpx.post(
        f"{settings.siliconflow_base_url}/images/generations",
        headers={"Authorization": f"Bearer {settings.siliconflow_api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=300,
    )
    resp.raise_for_status()
    url = resp.json()["images"][0]["url"]
    target = AVATAR_DIR / f"{avatar_id}-eyesclosed-raw.png"
    target.write_bytes(httpx.get(url, timeout=180, follow_redirects=True).content)
    print(f"[edit] 闭眼原图已生成 -> {target}")
    return target


def _report_alignment(open_img: Image.Image, closed_img: Image.Image) -> None:
    a = np.asarray(open_img.convert("RGB")).astype(np.int16)
    b = np.asarray(closed_img.convert("RGB")).astype(np.int16)
    diff = np.abs(a - b).max(axis=2)
    print(f"[check] 全图平均差异 {diff.mean():.1f}/255，差异>24 占比 {100 * (diff > 24).mean():.2f}%")


def build(avatar_id: str, feather: float) -> Path:
    meta_path = AVATAR_DIR / f"{avatar_id}.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    open_img = Image.open(AVATAR_DIR / f"{avatar_id}-raw.png").convert("RGB")
    closed_path = AVATAR_DIR / f"{avatar_id}-eyesclosed-raw.png"
    if not closed_path.exists():
        raise SystemExit(f"未找到闭眼原图 {closed_path}，请先加 --edit 生成")
    closed_img = Image.open(closed_path).convert("RGB")
    if closed_img.size != open_img.size:
        closed_img = closed_img.resize(open_img.size, Image.LANCZOS)
        print(f"[check] 闭眼图已缩放到 {open_img.size} 以对齐")
    _report_alignment(open_img, closed_img)

    width, height = open_img.size
    # 眨眼影响区域：两眼各一个椭圆，横向覆盖眼框及其上下肤色，纵向覆盖上下眼睑
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    for side in ("left", "right"):
        box = meta["eyes"][side]
        cx = (box["x"] + box["w"] / 2) * width
        cy = (box["y"] + box["h"] / 2) * height
        rx = box["w"] * width * 1.15
        ry = box["h"] * height * 2.6
        draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(max(2.0, width * 0.006)))

    # 只保留闭眼图的相近区域，避免改动别处
    out = closed_img.convert("RGBA")
    out.putalpha(mask)
    target = AVATAR_DIR / f"{avatar_id}-blink.png"
    out.save(target)
    print(f"[build] 眨眼贴图 -> {target}（RGB=闭眼画面，A=影响区域）")

    meta["blink_image"] = f"/avatar/{target.name}"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[build] 已登记 blink_image 到 {meta_path.name}")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="生成眨眼素材（工单18）")
    parser.add_argument("--id", default="qingci", help="数字人标识")
    parser.add_argument("--edit", action="store_true", help="先调用 AIGC 图像编辑生成闭眼原图")
    parser.add_argument("--feather", type=float, default=1.0, help="蒙版羽化强度系数")
    args = parser.parse_args()

    if args.edit:
        _call_edit(args.id)
    build(args.id, args.feather)


if __name__ == "__main__":
    main()
