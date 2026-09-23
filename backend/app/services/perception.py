"""工单18 · 实时行为与环境感知服务

工单编号：人工智能CV-AIGC-18-文旅Agent任务工单-智能导览与互动体验
职责（docs/04 §4.3）：编排 CV 深度图像任务（分类 / 检测跟踪 / 分割 / 手势 / 表情 / OCR），
并据此产出数字人的互动建议（如识别到「挥手」则主动问候）。

性能考量：
  · 检测与手势/表情为逐帧能力，启动即加载（YOLO11n 约 5MB、MediaPipe 模型约 19MB）；
  · 分割（SAM 2，约 74MB，CPU 单帧开销大）与 OCR（PaddleOCR）按需惰性加载，
    仅在显式请求 with_segments / with_ocr 时才初始化。
"""
from __future__ import annotations

from typing import Any

from ..providers.registry import (
    get_classifier,
    get_detector,
    get_expression,
    get_gesture,
    get_ocr,
    get_segmenter,
)
from ..providers.vision_tasks import (
    GESTURE_ACTIONS,
    Detection,
    ImageClassifier,
    MediaPipeExpressionRecognizer,
    MediaPipeGestureRecognizer,
    ObjectDetector,
    PerceptionResult,
    UltralyticsClassifier,
    UltralyticsDetector,
    UltralyticsSamSegmenter,
)

SEGMENT_EVERY_N = 6  # 分割开销较大，按帧间隔抽样执行


class PerceptionService:
    def __init__(self) -> None:
        self.classifier: ImageClassifier = get_classifier()
        self.detector: ObjectDetector = get_detector()
        self.gesture = get_gesture()
        self.expression = get_expression()
        self._segmenter = None
        self._ocr = None
        self._frame_index = 0

    # ---------------- 惰性能力 ----------------
    @property
    def segmenter(self):
        if self._segmenter is None:
            self._segmenter = get_segmenter()
        return self._segmenter

    @property
    def ocr(self):
        if self._ocr is None:
            self._ocr = get_ocr()
        return self._ocr

    @property
    def providers(self) -> dict[str, str]:
        """回显能力名称（读取类属性，不触发模型加载）。"""
        return {
            "classifier": UltralyticsClassifier.name,
            "detector": UltralyticsDetector.name,
            "segmenter": UltralyticsSamSegmenter.name,
            "gesture": MediaPipeGestureRecognizer.name,
            "expression": MediaPipeExpressionRecognizer.name,
            "ocr": "paddleocr",
        }

    # ---------------- 单帧感知 ----------------
    def analyze(
        self,
        frame: bytes,
        with_detection: bool = True,
        with_classify: bool = False,
        with_segments: bool = False,
        with_ocr: bool = False,
    ) -> PerceptionResult:
        self._frame_index += 1
        result = PerceptionResult()

        if with_classify:
            for label, score in self.classifier.classify(frame):
                result.classification.append(
                    Detection(label=label, score=float(score), box=[0.0, 0.0, 0.0, 0.0], track_id=None)
                )

        if with_detection:
            result.detections.extend(self.detector.detect(frame, track=True))

        if with_segments and self._frame_index % SEGMENT_EVERY_N == 1:
            result.segments = self.segmenter.segment(frame)

        if with_ocr:
            self.read_text(frame)

        result.gestures = self.gesture.recognize(frame)
        result.expression = self.expression.recognize(frame)
        return result

    # ---------------- OCR（碑刻 / 展板 / 指示牌）----------------
    def read_text(self, frame: bytes) -> str:
        rows = self.ocr.recognize(frame)
        return "\n".join(text for text, _ in rows)

    # ---------------- 互动建议 ----------------
    @staticmethod
    def suggest(result: PerceptionResult) -> dict[str, Any] | None:
        for gesture in result.gestures:
            plan = GESTURE_ACTIONS.get(gesture.name)
            if plan:
                return dict(plan, gesture=gesture.name, confidence=round(float(gesture.score), 3))
        return None

    @staticmethod
    def semantic_summary(result: PerceptionResult) -> dict[str, Any]:
        """提取给交互层使用的轻量语义摘要，不改变逐项感知结果。"""
        detection = max(result.detections, key=lambda item: item.score, default=None)
        gesture = next(
            (item for item in result.gestures if item.name in GESTURE_ACTIONS),
            None,
        )
        return {
            "target": detection.label if detection else None,
            "confidence": round(float(detection.score), 3) if detection else 0.0,
            "gesture": gesture.name if gesture else None,
        }

    # ---------------- 序列化 ----------------
    @staticmethod
    def to_payload(result: PerceptionResult) -> dict[str, Any]:
        return {
            # 图像分类：整图级标签，无位置信息
            "classification": [
                {"label": item.label, "score": round(float(item.score), 3)}
                for item in result.classification
            ],
            "detections": [
                {
                    "label": item.label,
                    "score": round(float(item.score), 3),
                    "box": [round(float(v), 4) for v in item.box],
                    "track_id": item.track_id,
                }
                for item in result.detections
            ],
            "segments": [
                {"label": item.label, "score": round(float(item.score), 3), "area_ratio": item.area_ratio}
                for item in result.segments
            ],
            "gestures": [
                {"name": item.name, "score": round(float(item.score), 3), "handedness": item.handedness, "wave": item.wave}
                for item in result.gestures
            ],
            "expression": (
                {
                    "name": result.expression.name,
                    "score": round(float(result.expression.score), 3),
                    "blendshapes": result.expression.blendshapes,
                }
                if result.expression
                else None
            ),
            "semantic": PerceptionService.semantic_summary(result),
        }
