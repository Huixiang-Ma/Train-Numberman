"""数字人视觉交互事件编排。"""
from __future__ import annotations

import time
from dataclasses import dataclass

from ..providers.vision_tasks import GESTURE_ACTIONS, PerceptionResult


@dataclass(frozen=True)
class InteractionEvent:
    kind: str
    text: str
    motion: str
    emotion: str
    target: str | None = None
    confidence: float = 0.0
    gesture: str | None = None


CLARIFICATION_TEXT = "我还不能确定你指的是什么，请重新拍摄或补充描述。"
_UNKNOWN_TARGET_KEY = "__unknown__"
_UNKNOWN_LABEL_MARKERS = ("未知", "不明", "unknown", "unidentified", "none", "null", "n/a")


class AvatarInteractionCoordinator:
    """把逐帧感知结果编排成可供上层消费的互动事件。"""

    def __init__(
        self,
        stable_frames: int = 3,
        cooldown_seconds: float = 20.0,
        min_confidence: float = 0.55,
    ) -> None:
        self.stable_frames = max(1, stable_frames)
        self.cooldown_seconds = max(0.0, cooldown_seconds)
        self.min_confidence = min_confidence
        self._stable_target: str | None = None
        self._stable_count = 0
        self._cooldowns: dict[str, float] = {}

    def observe(self, result: PerceptionResult) -> InteractionEvent | None:
        """观察一帧结果，必要时返回一个互动事件。"""
        gesture_event = self._gesture_event(result)
        if gesture_event is not None:
            self._reset_stable_target()
            return gesture_event

        detection = max(result.detections, key=lambda item: item.score, default=None)
        if detection is None:
            self._reset_stable_target()
            return None

        label = self._normalize_label(detection.label)
        stable_target = self._stable_key(label)
        if stable_target == self._stable_target:
            self._stable_count += 1
        else:
            self._stable_target = stable_target
            self._stable_count = 1

        if self._stable_count < self.stable_frames:
            return None

        now = time.monotonic()
        cooldown_key = self._cooldown_key(label)
        previous = self._cooldowns.get(cooldown_key)
        if previous is not None and now - previous < self.cooldown_seconds:
            return None

        self._cooldowns[cooldown_key] = now
        confidence = round(float(detection.score), 3)
        if self._is_unknown_label(label):
            return self._clarification_event(confidence=confidence)
        if detection.score < self.min_confidence:
            return self._clarification_event(confidence=confidence, target=label)

        return InteractionEvent(
            kind="explanation",
            text=f"请讲解{label}",
            motion="explain",
            emotion="curious",
            target=label,
            confidence=confidence,
        )

    @staticmethod
    def _normalize_label(label: str | None) -> str:
        return (label or "").strip()

    @classmethod
    def _is_unknown_label(cls, label: str) -> bool:
        normalized = label.casefold()
        return not normalized or any(marker in normalized for marker in _UNKNOWN_LABEL_MARKERS)

    @classmethod
    def _stable_key(cls, label: str) -> str:
        return _UNKNOWN_TARGET_KEY if cls._is_unknown_label(label) else label

    @classmethod
    def _cooldown_key(cls, label: str) -> str:
        return cls._stable_key(label)

    @staticmethod
    def _clarification_event(confidence: float, target: str | None = None) -> InteractionEvent:
        return InteractionEvent(
            kind="clarification",
            text=CLARIFICATION_TEXT,
            motion="nod",
            emotion="gentle",
            target=target,
            confidence=confidence,
        )

    def _gesture_event(self, result: PerceptionResult) -> InteractionEvent | None:
        for gesture in result.gestures:
            plan = GESTURE_ACTIONS.get(gesture.name)
            if plan is None:
                continue
            action = plan["action"]
            kind = {
                "greet": "greeting",
                "encourage": "encouragement",
                "recommend": "recommendation",
            }.get(action, action)
            emotion = "cheerful" if action == "greet" else "curious"
            return InteractionEvent(
                kind=kind,
                text=plan["text"],
                motion=plan["motion"],
                emotion=emotion,
                confidence=round(float(gesture.score), 3),
                gesture=gesture.name,
            )
        return None

    def _reset_stable_target(self) -> None:
        self._stable_target = None
        self._stable_count = 0


__all__ = ["AvatarInteractionCoordinator", "InteractionEvent"]
