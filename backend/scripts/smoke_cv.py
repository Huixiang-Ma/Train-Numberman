"""工单18 · CV 深度图像与实时感知自测

工单编号：人工智能CV-AIGC-18-文旅Agent任务工单-智能导览与互动体验
用法：python scripts/smoke_cv.py
说明：使用一张合成图像验证各能力可加载并正常推理（合成图中无目标时返回空结果是预期行为）。
"""
from __future__ import annotations

import io
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

from app.providers.registry import (  # noqa: E402
    get_classifier,
    get_detector,
    get_expression,
    get_gesture,
    get_segmenter,
)


def sample_frame(width: int = 640, height: int = 480) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (122, 148, 132)).save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


def main() -> None:
    frame = sample_frame()
    cases = [
        ("classifier", get_classifier, lambda model: model.classify(frame)),
        ("detector", get_detector, lambda model: model.detect(frame)),
        ("segmenter", get_segmenter, lambda model: model.segment(frame)),
        ("gesture", get_gesture, lambda model: model.recognize(frame)),
        ("expression", get_expression, lambda model: model.recognize(frame)),
    ]
    for label, factory, call in cases:
        started = time.time()
        try:
            model = factory()
            output = call(model)
            elapsed = time.time() - started
            print(f"[{label:11s}] {model.name:34s} {elapsed:6.1f}s -> {str(output)[:120]}")
        except Exception as exc:  # 单点失败不影响其余能力
            print(f"[{label:11s}] FAILED {type(exc).__name__}: {exc}")
    print("CV_SMOKE_DONE")


if __name__ == "__main__":
    main()
