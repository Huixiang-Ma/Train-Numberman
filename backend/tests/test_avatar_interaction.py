import pytest

from app.providers.vision_tasks import Detection, Gesture, PerceptionResult
from app.services.avatar_interaction import AvatarInteractionCoordinator


def gesture_result(name: str = "挥手") -> PerceptionResult:
    return PerceptionResult(gestures=[Gesture(name=name, score=0.94, wave=name == "挥手")])


def target_result(label: str = "古建筑", score: float = 0.91) -> PerceptionResult:
    return PerceptionResult(detections=[Detection(label=label, score=score, box=[0.2, 0.2, 0.3, 0.4])])


def test_gesture_event_returns_greeting_action():
    coordinator = AvatarInteractionCoordinator(stable_frames=3, cooldown_seconds=20)
    event = coordinator.observe(gesture_result())
    assert event is not None
    assert event.kind == "greeting"
    assert event.motion == "wave"
    assert event.text


def test_target_requires_three_stable_frames():
    coordinator = AvatarInteractionCoordinator(stable_frames=3, cooldown_seconds=20)
    assert coordinator.observe(target_result()) is None
    assert coordinator.observe(target_result()) is None
    event = coordinator.observe(target_result())
    assert event is not None
    assert event.kind == "explanation"
    assert event.target == "古建筑"
    assert event.motion == "explain"


def test_same_target_is_suppressed_during_cooldown():
    coordinator = AvatarInteractionCoordinator(stable_frames=3, cooldown_seconds=20)
    for _ in range(3):
        first = coordinator.observe(target_result())
    assert first is not None
    assert coordinator.observe(target_result()) is None


def test_low_confidence_target_returns_one_clarification_after_stability():
    coordinator = AvatarInteractionCoordinator(stable_frames=3, cooldown_seconds=20)
    assert coordinator.min_confidence == 0.55
    low_confidence = target_result(score=0.54)
    assert coordinator.observe(low_confidence) is None
    assert coordinator.observe(low_confidence) is None
    event = coordinator.observe(low_confidence)
    assert event is not None
    assert event.kind == "clarification"
    assert event.target == "古建筑"
    assert "重新拍摄" in event.text
    for _ in range(3):
        assert coordinator.observe(low_confidence) is None


@pytest.mark.parametrize("label", ["", "未知", "unknown"])
def test_empty_or_unknown_label_returns_clarification_without_target(label: str):
    coordinator = AvatarInteractionCoordinator(stable_frames=3, cooldown_seconds=20)
    result = target_result(label=label)
    assert coordinator.observe(result) is None
    assert coordinator.observe(result) is None
    event = coordinator.observe(result)
    assert event is not None
    assert event.kind == "clarification"
    assert event.target is None
    assert "请重新拍摄" in event.text


def test_same_target_can_trigger_again_at_cooldown_boundary(monkeypatch):
    now = [100.0]
    monkeypatch.setattr("app.services.avatar_interaction.time.monotonic", lambda: now[0])
    coordinator = AvatarInteractionCoordinator(stable_frames=3, cooldown_seconds=20)
    result = target_result()
    assert coordinator.observe(result) is None
    assert coordinator.observe(result) is None
    first = coordinator.observe(result)
    assert first is not None
    now[0] = 119.99
    assert coordinator.observe(result) is None
    now[0] = 120.0
    second = coordinator.observe(result)
    assert second is not None
    assert second.kind == "explanation"


def test_highest_score_detection_drives_stable_target():
    coordinator = AvatarInteractionCoordinator(stable_frames=3, cooldown_seconds=20)
    result = PerceptionResult(
        detections=[
            Detection(label="碑刻", score=0.80, box=[0.1, 0.1, 0.2, 0.2]),
            Detection(label="古建筑", score=0.92, box=[0.2, 0.2, 0.3, 0.4]),
        ]
    )
    assert coordinator.observe(result) is None
    assert coordinator.observe(result) is None
    event = coordinator.observe(result)
    assert event is not None
    assert event.target == "古建筑"
    assert event.confidence == 0.92


def test_target_change_resets_stability_counter():
    coordinator = AvatarInteractionCoordinator(stable_frames=3, cooldown_seconds=20)
    first_target = target_result(label="古建筑")
    second_target = target_result(label="碑刻")
    assert coordinator.observe(first_target) is None
    assert coordinator.observe(second_target) is None
    assert coordinator.observe(second_target) is None
    event = coordinator.observe(second_target)
    assert event is not None
    assert event.target == "碑刻"


def test_empty_frame_resets_stability_counter():
    coordinator = AvatarInteractionCoordinator(stable_frames=3, cooldown_seconds=20)
    result = target_result()
    assert coordinator.observe(result) is None
    assert coordinator.observe(PerceptionResult()) is None
    assert coordinator.observe(result) is None
    assert coordinator.observe(result) is None
    event = coordinator.observe(result)
    assert event is not None
    assert event.target == "古建筑"
