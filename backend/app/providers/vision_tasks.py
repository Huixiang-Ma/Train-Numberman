"""工单18 · CV 深度图像与实时感知能力层

工单编号：人工智能CV-AIGC-18-文旅Agent任务工单-智能导览与互动体验
技术栈（docs/01）：
  图像分类   Ultralytics YOLO11-cls
  目标检测   Ultralytics YOLO11 + ByteTrack 连续帧跟踪（persist=True）
  图像分割   Ultralytics SAM 2
  手势识别   MediaPipe GestureRecognizer + 手部关键点时序判定「挥手」
  表情识别   MediaPipe FaceLandmarker + blendshapes

全部为主选实现，本地权重轻量（YOLO11 约 5MB、MediaPipe 模型约 19MB），不提供替代实现。
"""
from __future__ import annotations

import io
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence


# --------------------------------------------------------------------------
# 数据结构
# --------------------------------------------------------------------------
@dataclass
class Detection:
    label: str
    score: float
    box: list[float]  # 归一化 [x, y, w, h]
    track_id: int | None = None


@dataclass
class Segment:
    label: str
    score: float
    area_ratio: float


@dataclass
class Gesture:
    name: str
    score: float
    handedness: str = ""
    wave: bool = False


@dataclass
class Expression:
    name: str
    score: float
    blendshapes: dict[str, float] = field(default_factory=dict)


@dataclass
class PerceptionResult:
    detections: list[Detection] = field(default_factory=list)
    # 图像分类结果单独成组：分类只回答"整张图是什么"，没有位置框。
    # 此前把分类结果并入 detections 并填一个全 0 的框，前端按框绘制时
    # 会在画面左上角画出一堆零尺寸标注（工单20 集成测试实测到该问题）。
    classification: list[Detection] = field(default_factory=list)
    segments: list[Segment] = field(default_factory=list)
    gestures: list[Gesture] = field(default_factory=list)
    expression: Expression | None = None


# 文旅场景标签收敛（YOLO 通用类别 → 场景语义）
SCENE_LABELS = ["古建筑", "碑刻", "壁画", "雕塑", "动植物", "指示牌", "游客", "文物展柜"]
SCENE_HINTS = {
    "person": "游客",
    "bench": "休息点",
    "potted plant": "动植物",
    "vase": "文物展柜",
    "clock": "指示牌",
    "book": "碑刻",
    "bottle": "文物展柜",
}

# MediaPipe 手势标签 → 中文
GESTURE_LABELS_ZH = {
    "None": "无手势",
    "Closed_Fist": "握拳",
    "Open_Palm": "张开手掌",
    "Pointing_Up": "指向",
    "Thumb_Down": "点踩",
    "Thumb_Up": "点赞",
    "Victory": "比耶",
    "ILoveYou": "比心",
}

# 手势 → 数字人互动动作（供 perception 服务生成建议）
GESTURE_ACTIONS = {
    "挥手": {"action": "greet", "motion": "wave", "text": "你好呀，欢迎来到景区，需要我为你介绍一下吗？"},
    "点赞": {"action": "encourage", "motion": "nod", "text": "谢谢你的认可，我继续为你讲解。"},
    "指向": {"action": "recommend", "motion": "point", "text": "你指的是这个方向，那里有几处值得一看的景致。"},
    "比心": {"action": "greet", "motion": "wave", "text": "收到你的比心，愿你此行愉快。"},
}


# --------------------------------------------------------------------------
# 接口
# --------------------------------------------------------------------------
class ImageClassifier(ABC):
    name: str = "base"

    @abstractmethod
    def classify(self, image: bytes) -> list[tuple[str, float]]: ...


class ObjectDetector(ABC):
    name: str = "base"

    @abstractmethod
    def detect(self, image: bytes, track: bool = True) -> list[Detection]: ...


class Segmenter(ABC):
    name: str = "base"

    @abstractmethod
    def segment(self, image: bytes, label: str | None = None) -> list[Segment]: ...


class GestureRecognizer(ABC):
    name: str = "base"

    @abstractmethod
    def recognize(self, frame: bytes) -> list[Gesture]: ...


class ExpressionRecognizer(ABC):
    name: str = "base"

    @abstractmethod
    def recognize(self, frame: bytes) -> Expression | None: ...


# --------------------------------------------------------------------------
# YOLO11：分类 / 检测跟踪
# --------------------------------------------------------------------------
class UltralyticsClassifier(ImageClassifier):
    name = "ultralytics:yolo11-cls"

    def __init__(self, model: str = "yolo11n-cls.pt") -> None:
        from ultralytics import YOLO

        self.model_name = model
        self._model = YOLO(model)

    def _to_array(self, image: bytes):
        import numpy as np
        from PIL import Image

        return np.array(Image.open(io.BytesIO(image)).convert("RGB"))

    def classify(self, image: bytes) -> list[tuple[str, float]]:
        result = self._model.predict(self._to_array(image), verbose=False)[0]
        names = result.names
        probs = getattr(result, "probs", None)
        if probs is None:
            return []
        return [(str(names[int(i)]), float(probs.data[int(i)])) for i in probs.top5[:5]]


class UltralyticsDetector(ObjectDetector):
    name = "ultralytics:yolo11+bytetrack"

    def __init__(self, model: str = "yolo11n.pt", conf: float = 0.35) -> None:
        from ultralytics import YOLO

        self.model_name = model
        self.conf = conf
        self._model = YOLO(model)
        self._lock = threading.Lock()

    def detect(self, image: bytes, track: bool = True) -> list[Detection]:
        import numpy as np
        from PIL import Image

        arr = np.array(Image.open(io.BytesIO(image)).convert("RGB"))
        height, width = arr.shape[:2]
        with self._lock:
            if track:
                # persist=True：跨帧保持轨迹，内部即为 ByteTrack
                result = self._model.track(arr, conf=self.conf, persist=True, verbose=False)[0]
            else:
                result = self._model.predict(arr, conf=self.conf, verbose=False)[0]

        rows: list[Detection] = []
        for box in result.boxes:
            x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].tolist()]
            raw_label = str(result.names[int(box.cls[0])])
            track_id = int(box.id[0]) if getattr(box, "id", None) is not None else None
            rows.append(
                Detection(
                    label=SCENE_HINTS.get(raw_label, raw_label),
                    score=float(box.conf[0]),
                    box=[x1 / width, y1 / height, (x2 - x1) / width, (y2 - y1) / height],
                    track_id=track_id,
                )
            )
        return rows


class UltralyticsSamSegmenter(Segmenter):
    name = "ultralytics:sam2"

    def __init__(self, model: str = "sam2.1_t.pt") -> None:
        from ultralytics import SAM

        self.model_name = model
        self._model = SAM(model)

    def segment(self, image: bytes, label: str | None = None) -> list[Segment]:
        import numpy as np
        from PIL import Image

        arr = np.array(Image.open(io.BytesIO(image)).convert("RGB"))
        result = self._model(arr, verbose=False)[0]
        masks = getattr(result, "masks", None)
        if masks is None or masks.data is None:
            return []

        total = arr.shape[0] * arr.shape[1]
        boxes = getattr(result, "boxes", None)
        confs = boxes.conf.tolist() if boxes is not None and boxes.conf is not None else []
        segments: list[Segment] = []
        for index, mask in enumerate(masks.data):
            area = float(mask.sum()) / total
            score = float(confs[index]) if index < len(confs) else 0.0
            segments.append(Segment(label=label or "前景", score=score, area_ratio=round(area, 4)))
        return segments

    def cutout_person(self, image: bytes) -> bytes | None:
        """抠出照片中的人物主体，返回透明底 PNG（工单19 · 虚拟合影）。

        为什么不直接用上面的 segment()：
          SAM 2 的自动模式（无提示）会把画面切成大量碎片（实测在浅色衣料 + 浅色背景上
          尤其明显），无法当作人物抠图使用。这里走标准两步流水线：
            YOLO 检出 person 框 → 以框作为 SAM 2 的提示分割 → 取并集并做形态学清理。
        未检出人物时返回 None，由调用方决定降级策略，不让合成链路在此中断。
        """
        import numpy as np
        from PIL import Image
        from scipy import ndimage

        # 延迟导入：本模块被 registry 导入，模块级互相导入会成环
        from .registry import get_detector

        arr = np.array(Image.open(io.BytesIO(image)).convert("RGB"))
        height, width = arr.shape[:2]

        detections = get_detector().detect(image, track=False)
        boxes = [
            [
                d.box[0] * width,
                d.box[1] * height,
                (d.box[0] + d.box[2]) * width,
                (d.box[1] + d.box[3]) * height,
            ]
            for d in detections
            if d.label == "游客" and d.box[2] * d.box[3] > 0.02  # 剔除过小的误检
        ]
        if not boxes:
            return None

        result = self._model(arr, bboxes=boxes, verbose=False)[0]
        masks = getattr(result, "masks", None)
        if masks is None or masks.data is None or len(masks.data) == 0:
            return None

        union = (masks.data.cpu().numpy() > 0.5).any(axis=0)
        union = ndimage.binary_closing(union, structure=np.ones((7, 7)))
        union = ndimage.binary_fill_holes(union)
        labels, count = ndimage.label(union)
        if count > 1:
            # 多人合影保留所有主要人物，剔除零碎噪点
            sizes = ndimage.sum(union, labels, range(1, count + 1))
            threshold = float(np.max(sizes)) * 0.25
            union = np.isin(labels, [i + 1 for i, size in enumerate(sizes) if size >= threshold])

        alpha = (ndimage.gaussian_filter(union.astype("float32"), 1.2) * 255).clip(0, 255).astype("uint8")
        if int(alpha.max()) == 0:
            return None

        buffer = io.BytesIO()
        Image.fromarray(np.dstack([arr, alpha]), "RGBA").save(buffer, format="PNG")
        return buffer.getvalue()


# --------------------------------------------------------------------------
# MediaPipe：手势 / 表情
# --------------------------------------------------------------------------
class MediaPipeGestureRecognizer(GestureRecognizer):
    """MediaPipe GestureRecognizer + 手部关键点时序判定「挥手」。"""

    name = "mediapipe:gesture"
    WAVE_WINDOW = 12          # 参与判定的帧数
    WAVE_MIN_AMPLITUDE = 0.06  # 腕部横向摆幅阈值（归一化坐标）
    WAVE_MIN_DIRECTIONS = 2    # 至少发生两次方向反转

    def __init__(self, model_path: str | Path) -> None:
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        path = Path(model_path)
        if not path.exists():
            raise RuntimeError(f"未找到 MediaPipe 手势模型：{path}（请执行 download_models.py mediapipe）")

        # 注意：MediaPipe 的 C++ 层无法打开含非 ASCII 字符的路径（本项目路径含中文），
        # 因此以内存缓冲方式加载模型。
        self._model_bytes = path.read_bytes()
        self._mp = __import__("mediapipe")
        self._lock = threading.Lock()
        options = vision.GestureRecognizerOptions(
            base_options=mp_python.BaseOptions(model_asset_buffer=self._model_bytes),
            num_hands=2,
            running_mode=vision.RunningMode.IMAGE,
            min_hand_detection_confidence=0.4,
            min_tracking_confidence=0.4,
        )
        self._recognizer = vision.GestureRecognizer.create_from_options(options)
        self._history: dict[str, deque] = {}

    def _to_mp_image(self, frame: bytes):
        import numpy as np
        from PIL import Image

        arr = np.array(Image.open(io.BytesIO(frame)).convert("RGB"))
        return self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=arr)

    def _is_waving(self, handedness: str, wrist_x: float, now: float) -> bool:
        history = self._history.setdefault(handedness or "unknown", deque(maxlen=self.WAVE_WINDOW))
        history.append((wrist_x, now))
        if len(history) < self.WAVE_WINDOW:
            return False
        xs = [item[0] for item in history]
        if max(xs) - min(xs) < self.WAVE_MIN_AMPLITUDE:
            return False
        deltas = [xs[i + 1] - xs[i] for i in range(len(xs) - 1)]
        directions = [1 if d > 0.004 else (-1 if d < -0.004 else 0) for d in deltas]
        reversals = sum(
            1 for i in range(1, len(directions)) if directions[i] and directions[i - 1] and directions[i] != directions[i - 1]
        )
        return reversals >= self.WAVE_MIN_DIRECTIONS

    def recognize(self, frame: bytes) -> list[Gesture]:
        mp_image = self._to_mp_image(frame)
        with self._lock:
            result = self._recognizer.recognize(mp_image)

        now = time.time()
        rows: list[Gesture] = []
        gesture_groups = getattr(result, "gestures", None) or []
        landmark_groups = getattr(result, "hand_landmarks", None) or []

        for index, categories in enumerate(gesture_groups):
            top = categories[0] if categories else None
            raw_name = getattr(top, "category_name", "None") if top else "None"
            score = float(getattr(top, "score", 0.0)) if top else 0.0
            handedness = ""
            if index < len(landmark_groups) and landmark_groups[index]:
                wrist = landmark_groups[index][0]
                # MediaPipe 未直接给左右手，这里用腕部相对画面的位置作为稳定标识
                handedness = "left" if wrist.x < 0.5 else "right"

            wave = False
            if index < len(landmark_groups) and landmark_groups[index]:
                wrist_x = float(landmark_groups[index][0].x)
                wave = self._is_waving(handedness, wrist_x, now)

            label = "挥手" if (wave and raw_name in {"Open_Palm", "None", "Pointing_Up"}) else GESTURE_LABELS_ZH.get(raw_name, raw_name)
            rows.append(Gesture(name=label, score=score, handedness=handedness, wave=wave))
        return rows


class MediaPipeExpressionRecognizer(ExpressionRecognizer):
    """MediaPipe FaceLandmarker + blendshapes → 情绪判定。"""

    name = "mediapipe:face-landmarker"

    def __init__(self, model_path: str | Path) -> None:
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        path = Path(model_path)
        if not path.exists():
            raise RuntimeError(f"未找到 MediaPipe 人脸模型：{path}（请执行 download_models.py mediapipe）")

        # 同上：以内存缓冲加载，规避 MediaPipe 对非 ASCII 路径的限制
        self._model_bytes = path.read_bytes()
        self._mp = __import__("mediapipe")
        self._lock = threading.Lock()
        options = vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_buffer=self._model_bytes),
            num_faces=1,
            output_face_blendshapes=True,
            running_mode=vision.RunningMode.IMAGE,
            min_face_detection_confidence=0.4,
        )
        self._landmarker = vision.FaceLandmarker.create_from_options(options)

    def _to_mp_image(self, frame: bytes):
        import numpy as np
        from PIL import Image

        arr = np.array(Image.open(io.BytesIO(frame)).convert("RGB"))
        return self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=arr)

    @staticmethod
    def _classify(scores: dict[str, float]) -> tuple[str, float]:
        smile = (scores.get("mouthSmileLeft", 0.0) + scores.get("mouthSmileRight", 0.0)) / 2
        brow = scores.get("browInnerUp", 0.0)
        blink = (scores.get("eyeBlinkLeft", 0.0) + scores.get("eyeBlinkRight", 0.0)) / 2

        if smile >= 0.35:
            return "happy", smile
        if brow >= 0.40:
            return "curious", brow
        if blink >= 0.55:
            return "tired", blink
        return "neutral", max(0.0, 1.0 - max(smile, brow, blink))

    def recognize(self, frame: bytes) -> Expression | None:
        mp_image = self._to_mp_image(frame)
        with self._lock:
            result = self._landmarker.detect(mp_image)

        blendshape_groups = getattr(result, "face_blendshapes", None) or []
        if not blendshape_groups or not blendshape_groups[0]:
            return None

        scores = {
            item.category_name: float(item.score)
            for item in blendshape_groups[0]
            if getattr(item, "category_name", None)
        }
        name, score = self._classify(scores)
        key_scores = {
            key: round(scores[key], 3)
            for key in ("mouthSmileLeft", "mouthSmileRight", "browInnerUp", "eyeBlinkLeft", "eyeBlinkRight")
            if key in scores
        }
        return Expression(name=name, score=round(score, 3), blendshapes=key_scores)


__all__: Sequence[str] = [
    "Detection",
    "Expression",
    "Gesture",
    "GESTURE_ACTIONS",
    "PerceptionResult",
    "Segment",
    "SCENE_LABELS",
]
