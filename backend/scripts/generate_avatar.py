"""工单18 · 用 AIGC 图像生成模型产出数字人形象

工单编号：人工智能CV-AIGC-18-文旅Agent任务工单-智能导览与互动体验
依据：工单18 要求「虚拟数字人形象须使用图像生成模型或 AIGC 工具生成」。

实现：调用 SiliconFlow 图像生成接口（AIGC 文生图）产出「国风女性讲解员」半身正面像，
      随后可直接串联 prepare_avatar.py 完成抠图与口型区定位。

用法：
  python scripts/generate_avatar.py                 # 生成并落盘原图
  python scripts/generate_avatar.py --no-prepare     # 仅生成，不做抠图/定位
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings  # noqa: E402

AVATAR_DIR = ROOT.parent / "frontend" / "public" / "avatar"

# 依次尝试的文生图模型（均为 AIGC 图像生成模型）
CANDIDATE_MODELS = [
    "Qwen/Qwen-Image",
    "Kwai-Kolors/Kolors",
    "stabilityai/stable-diffusion-3-5-large",
]

PROMPT = (
    "国风女性数字人讲解员，半身正面肖像，站姿端庄，"
    "双手在腹部前方自然交叠相握、右手轻搭在左手之上，双臂自然下垂微微弯曲，"
    "20 多岁，气质亲和温和，现代改良交领汉服，暖米白与琥珀金配色衣料，"
    "简约发髻配小巧玉簪，正脸平视镜头，表情温和自然，"
    "嘴唇自然闭合不露牙齿，眼神平静注视镜头，双眼自然睁开，"
    "柔和暖调影棚布光，面部光线均匀清晰，皮肤质感细腻，写实高质量渲染，"
    "纯白色干净背景，上半身与双手完整入画，人物居中，头顶留少量空间"
)

NEGATIVE_PROMPT = "文字, 水印, 签名, 边框, 多人, 侧脸, 张嘴大笑, 复杂背景, 卡通, 变形, 低清晰度"


def generate(model: str, width: int, height: int, seed: int | None) -> str:
    settings = get_settings()
    if not settings.siliconflow_api_key:
        raise SystemExit("未配置 SILICONFLOW_API_KEY，无法调用图像生成接口")

    payload = {
        "model": model,
        "prompt": PROMPT,
        "negative_prompt": NEGATIVE_PROMPT,
        "image_size": f"{width}x{height}",
        "batch_size": 1,
        "num_inference_steps": 30,
        "guidance_scale": 7.5,
    }
    if seed is not None:
        payload["seed"] = seed

    with httpx.Client(timeout=300.0) as client:
        response = client.post(
            f"{settings.siliconflow_base_url.rstrip('/')}/images/generations",
            headers={"Authorization": f"Bearer {settings.siliconflow_api_key}", "Content-Type": "application/json"},
            json=payload,
        )
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:300]}")

    images = response.json().get("images") or []
    if not images:
        raise RuntimeError(f"接口未返回图像：{response.text[:300]}")
    return images[0]["url"]


def download(url: str, target: Path) -> None:
    with httpx.Client(timeout=180.0, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
    target.write_bytes(response.content)


def main() -> None:
    parser = argparse.ArgumentParser(description="AIGC 生成数字人形象（工单18）")
    parser.add_argument("--id", default="qingci", help="数字人标识，用于输出文件名")
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=1536)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--model", default=None, help="指定模型；默认按候选列表依次尝试")
    parser.add_argument("--no-prepare", action="store_true", help="仅生成，不执行抠图与关键点定位")
    parser.add_argument("--method", default="keying", choices=["keying", "sam", "rembg"], help="去背景方式")
    args = parser.parse_args()

    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = AVATAR_DIR / f"{args.id}-raw.png"

    models = [args.model] if args.model else CANDIDATE_MODELS
    last_error = ""
    for model in models:
        started = time.time()
        print(f"[generate] 尝试模型 {model} …")
        try:
            url = generate(model, args.width, args.height, args.seed)
            download(url, raw_path)
            print(f"[generate] 成功 {model}（{time.time() - started:.1f}s）-> {raw_path}")
            print(f"[generate] 图像地址：{url}")
            break
        except Exception as exc:  # 依次尝试下一个候选模型
            last_error = f"{model}: {type(exc).__name__}: {exc}"
            print(f"[generate] 失败 {last_error}")
    else:
        raise SystemExit(f"所有候选模型均失败，最后一个错误：{last_error}")

    if args.no_prepare:
        return

    print("[prepare] 执行抠图与人脸关键点定位 …")
    import json as _json

    from PIL import Image
    from prepare_avatar import cutout, detect_regions  # 同目录脚本

    cutout_path = AVATAR_DIR / f"{args.id}-cutout.png"
    cutout(raw_path, cutout_path, method=args.method)
    print(f"[prepare] 抠图完成 -> {cutout_path}")

    meta = detect_regions(raw_path)
    meta["image"] = f"/avatar/{cutout_path.name}"
    meta_path = AVATAR_DIR / f"{args.id}.json"
    meta_path.write_text(_json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[prepare] 口型/头部区域 -> {meta_path}")
    print(_json.dumps(meta, ensure_ascii=False))
    with Image.open(cutout_path) as image:
        print(f"[prepare] 输出尺寸 {image.size}")


if __name__ == "__main__":
    main()
