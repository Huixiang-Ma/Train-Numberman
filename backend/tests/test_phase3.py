"""工单18 · 阶段三接口测试（对接真实技术栈）

工单编号：人工智能CV-AIGC-18-文旅Agent任务工单-智能导览与互动体验
覆盖：会话（Redis）/ 数字人对话（LangGraph）/ 数字人驱动（CosyVoice）/ 实时感知（YOLO11+MediaPipe）
"""
from __future__ import annotations

import io

from app.providers.base import Hit, KbChunkData
from app.providers.vision_tasks import Detection, Gesture, PerceptionResult


def sample_frame(width: int = 480, height: int = 360) -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (122, 148, 132)).save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()


def _target_result() -> PerceptionResult:
    return PerceptionResult(detections=[Detection(label="古建筑", score=0.92, box=[0.1, 0.1, 0.4, 0.4])])


def _wave_result() -> PerceptionResult:
    return PerceptionResult(gestures=[Gesture(name="挥手", score=0.94, wave=True)])


class StubPerceptionService:
    def __init__(self, result: PerceptionResult):
        self.result = result
        self.providers = {
            "classifier": "stub:classifier",
            "detector": "stub:detector",
            "segmenter": "stub:segmenter",
            "gesture": "stub:gesture",
            "expression": "stub:expression",
            "ocr": "stub:ocr",
        }

    def analyze(self, *args, **kwargs) -> PerceptionResult:
        return self.result

    @staticmethod
    def to_payload(result: PerceptionResult) -> dict:
        return {
            "classification": [],
            "detections": [
                {"label": item.label, "score": item.score, "box": item.box, "track_id": item.track_id}
                for item in result.detections
            ],
            "segments": [],
            "gestures": [
                {"name": item.name, "score": item.score, "handedness": item.handedness, "wave": item.wave}
                for item in result.gestures
            ],
            "expression": None,
        }

    @staticmethod
    def suggest(result: PerceptionResult) -> dict | None:
        if result.gestures:
            return {"action": "greet", "motion": "wave", "text": "你好", "gesture": "挥手", "confidence": 0.94}
        return None


class StubRetrievalService:
    calls: list[tuple[str, int]] = []
    hits: list[Hit] = []

    def text_to_text(self, query: str, top_k: int) -> list[Hit]:
        self.calls.append((query, top_k))
        return list(self.hits)


class StubGenerationService:
    calls: list[tuple[str, list[Hit]]] = []
    text = "古建筑讲解：这是一处保存完整的传统建筑。"

    def generate_with_status(self, query: str, hits: list[Hit], lang: str = "zh") -> tuple[str, bool]:
        self.calls.append((query, list(hits)))
        return self.text, False

    def generate(self, query: str, hits: list[Hit], lang: str = "zh") -> str:
        text, _ = self.generate_with_status(query, hits, lang)
        return text


class StubAvatarService:
    drives: list[tuple[str, str, str]] = []
    greetings: list[str | None] = []

    def drive(self, text: str, lang: str = "zh", emotion: str | None = None, motion: str | None = None) -> dict:
        self.drives.append((text, emotion or "", motion or ""))
        return {
            "avatar_id": "stub",
            "emotion": emotion or "calm",
            "style": "stub",
            "motion": motion or "explain",
            "audio": None,
            "visemes": [{"t": 0, "viseme": "A", "char": text[:1]}],
            "duration_ms": 100,
            "lipsync": "viseme",
            "degraded": "",
        }

    def greet(self, gesture: str | None = None, lang: str = "zh") -> dict:
        self.greetings.append(gesture)
        drive = self.drive("你好", lang=lang, emotion="cheerful", motion="wave")
        return {"text": "你好", "gesture": gesture or "挥手", "drive": drive}

def _stub_hit() -> Hit:
    return Hit(
        chunk=KbChunkData(id="kb-1", title="古建筑", content="传统木构建筑资料", source="景区档案"),
        score=0.95,
    )


# ------------------------------ 数字人 ------------------------------
def test_avatar_profile(client):
    data = client.get("/api/v1/avatar").json()["data"]
    assert data["avatar_id"]
    assert data["engine"]["3d"] == "three.js"
    assert "emotions" in data and "motions" in data
    assert data["voice"]["provider"]


def test_avatar_drive_returns_visemes_and_audio(client):
    """驱动数据契约（工单20 修订）。

    语音合成走云端额度，不可用时**按设计降级为无声驱动**（见 services/avatar.py）：
    返回 visemes 与 duration_ms 供前端按视位时间轴播报，audio 为 null 并附 degraded 说明。
    因此这里不再把"一定有音频"当成硬契约，而是校验两种形态都自洽。
    """
    data = client.post("/api/v1/avatar/drive", json={"text": "欢迎来到景区"}).json()["data"]
    assert data["visemes"], "唇形视位不应为空"
    assert data["duration_ms"] > 0
    assert data["motion"]
    if data["audio"] is None:
        # 降级形态：必须说明原因，且视位/时长仍然可用（前端无声演示）
        assert data.get("degraded"), "无声驱动必须给出降级原因"
    else:
        assert data["audio"]["base64"], "CosyVoice 应返回音频数据"
        assert data["audio"]["provider"].startswith("siliconflow")


def test_avatar_greet_by_gesture(client):
    data = client.post("/api/v1/avatar/greet", json={"gesture": "挥手"}).json()["data"]
    assert data["text"]
    assert data["drive"]["motion"] == "wave"


# ------------------------------ 会话（Redis）------------------------------
def test_session_lifecycle_on_redis(client):
    created = client.post("/api/v1/session", json={"lang": "zh"}).json()["data"]
    assert created["store"] == "redis", "会话主选应为 Redis"
    session_id = created["id"]

    assert client.get(f"/api/v1/session/{session_id}").json()["data"]["id"] == session_id
    assert client.delete(f"/api/v1/session/{session_id}").json()["data"]["closed"] == session_id
    assert client.get(f"/api/v1/session/{session_id}").status_code == 404


# ------------------------------ 多轮对话 ------------------------------
def test_dialog_multi_turn_with_context(client):
    first = client.post("/api/v1/dialog", json={"text": "主殿的木构有什么特点", "with_avatar": False}).json()["data"]
    assert first["session_id"]
    assert first["answer_text"]
    assert first["intent"] in {"知识", "识物", "寻路", "活动", "美食", "互动"}
    assert first["avatar"] is None

    second = client.post(
        "/api/v1/dialog", json={"session_id": first["session_id"], "text": "那壁画呢", "with_avatar": False}
    ).json()["data"]
    assert second["session_id"] == first["session_id"]

    session = client.get(f"/api/v1/session/{first['session_id']}").json()["data"]
    assert len(session["turns"]) >= 4


def test_dialog_with_avatar_drive(client):
    data = client.post("/api/v1/dialog", json={"text": "你好", "with_avatar": True}).json()["data"]
    assert data["avatar"] is not None
    assert data["avatar"]["visemes"]


def test_dialog_multimodal_with_image_perception(client):
    files = {"image": ("frame.jpg", sample_frame(), "image/jpeg")}
    data = client.post("/api/v1/dialog/multimodal", files=files, data={"text": "这是什么", "with_avatar": "false"}).json()["data"]
    assert data["answer_text"]
    assert data["perception"] is not None
    assert "detections" in data["perception"]
    assert "gestures" in data["perception"]


# ------------------------------ 实时感知 ------------------------------
def test_perception_analyze_rest(client):
    files = {"frame": ("frame.jpg", sample_frame(), "image/jpeg")}
    data = client.post("/api/v1/perception/analyze", files=files).json()["data"]
    assert "detections" in data and "gestures" in data
    providers = data["providers"]
    assert providers["detector"].startswith("ultralytics")
    assert providers["gesture"].startswith("mediapipe")
    assert providers["segmenter"].startswith("ultralytics")


def test_perception_rejects_invalid_frame(client):
    files = {"frame": ("bad.jpg", b"\xff\xd8\xff\xe0not-image", "image/jpeg")}
    assert client.post("/api/v1/perception/analyze", files=files).status_code == 400


def test_perception_websocket_stream(client, monkeypatch):
    import app.api.v1.perception as perception_api

    stub_perception = StubPerceptionService(_target_result())
    stub_perception.providers["gesture"] = "mediapipe:gesture"
    monkeypatch.setattr(perception_api, "PerceptionService", lambda: stub_perception)
    monkeypatch.setattr(perception_api, "AvatarService", StubAvatarService)

    with client.websocket_connect("/api/v1/ws/perception") as ws:
        ready = ws.receive_json()
        assert ready["type"] == "ready"
        assert ready["providers"]["gesture"].startswith("mediapipe")

        ws.send_bytes(sample_frame(320, 240))
        message = ws.receive_json()
        assert message["type"] == "perception"
        assert "detections" in message["data"]
        assert message["interaction"] is None

        ws.send_text('{"ping": true}')
        assert ws.receive_json()["type"] == "pong"


def test_avatar_interaction_settings_are_configurable():
    from app.core.config import Settings

    defaults = Settings(_env_file=None)
    assert defaults.avatar_stable_frames == 3
    assert defaults.avatar_auto_explain_cooldown_seconds == 20.0
    assert defaults.avatar_auto_explain_top_k == 3

    settings = Settings(
        avatar_stable_frames=5,
        avatar_auto_explain_cooldown_seconds=12.5,
        avatar_auto_explain_top_k=4,
    )
    assert settings.avatar_stable_frames == 5
    assert settings.avatar_auto_explain_cooldown_seconds == 12.5
    assert settings.avatar_auto_explain_top_k == 4


def test_perception_semantic_summary_prefers_highest_confidence_target():
    from app.services.perception import PerceptionService

    result = PerceptionResult(
        detections=[
            Detection(label="碑刻", score=0.61, box=[0.0, 0.0, 0.1, 0.1]),
            Detection(label="古建筑", score=0.92, box=[0.1, 0.1, 0.4, 0.4]),
        ]
    )
    assert PerceptionService.semantic_summary(result) == {
        "target": "古建筑",
        "confidence": 0.92,
        "gesture": None,
    }


def test_perception_websocket_generation_service_degradation_contract(monkeypatch):
    import app.services.generation as generation_module

    class FailingLlm:
        def generate(self, *args, **kwargs):
            raise RuntimeError("llm unavailable")

    monkeypatch.setattr(generation_module, "get_llm", FailingLlm)
    service = generation_module.GenerationService()

    text, degraded = service.generate_with_status("古建筑", [_stub_hit()])

    assert degraded is True
    assert "讲解服务暂时繁忙" in text
    assert service.generate("古建筑", [_stub_hit()]) == text


def test_perception_websocket_real_generation_degradation_is_clarification(client, monkeypatch):
    import app.api.v1.perception as perception_api
    import app.services.generation as generation_module

    class FailingLlm:
        def generate(self, *args, **kwargs):
            raise RuntimeError("llm unavailable")

    stub_perception = StubPerceptionService(_target_result())
    StubRetrievalService.hits = [_stub_hit()]
    monkeypatch.setattr(generation_module, "get_llm", FailingLlm)
    monkeypatch.setattr(perception_api, "PerceptionService", lambda: stub_perception)
    monkeypatch.setattr(perception_api, "RetrievalService", StubRetrievalService)
    monkeypatch.setattr(perception_api, "GenerationService", generation_module.GenerationService)
    monkeypatch.setattr(perception_api, "AvatarService", StubAvatarService)

    with client.websocket_connect("/api/v1/ws/perception") as ws:
        assert ws.receive_json()["type"] == "ready"
        for _ in range(3):
            ws.send_bytes(sample_frame(320, 240))
            message = ws.receive_json()

    assert message["interaction"]["kind"] == "clarification"
    assert "资料来源：" not in message["interaction"]["text"]


def test_perception_websocket_auto_explanation_contract(client, monkeypatch):
    import app.api.v1.perception as perception_api

    stub_perception = StubPerceptionService(_target_result())
    StubRetrievalService.calls = []
    StubRetrievalService.hits = [_stub_hit()]
    StubGenerationService.calls = []
    StubAvatarService.drives = []
    StubAvatarService.greetings = []
    monkeypatch.setattr(perception_api, "PerceptionService", lambda: stub_perception)
    monkeypatch.setattr(perception_api, "RetrievalService", StubRetrievalService)
    monkeypatch.setattr(perception_api, "GenerationService", StubGenerationService, raising=False)
    monkeypatch.setattr(perception_api, "AvatarService", StubAvatarService)

    with client.websocket_connect("/api/v1/ws/perception") as ws:
        assert ws.receive_json()["type"] == "ready"
        for index in range(9):
            ws.send_bytes(sample_frame(320, 240))
            message = ws.receive_json()
            assert message["type"] == "perception"
            if index < 2 or index > 2:
                assert message["interaction"] is None
            else:
                interaction = message["interaction"]
                assert interaction["kind"] == "explanation"
                assert interaction["target"] == "古建筑"
                assert interaction["confidence"] == 0.92
                assert interaction["motion"] == "explain"
                assert interaction["emotion"] == "curious"
                assert interaction["text"] == "古建筑讲解：这是一处保存完整的传统建筑。资料来源：古建筑（景区档案）。"
                assert interaction["drive"]["motion"] == "explain"
                assert set(message["avatar"]) == {"text", "gesture", "drive"}
                assert message["avatar"]["text"] == interaction["text"]
                assert message["avatar"]["gesture"] == "古建筑"
                assert message["avatar"]["drive"] == interaction["drive"]

    assert StubRetrievalService.calls == [("古建筑", 3)]
    assert StubGenerationService.calls[0][0] == "古建筑"
    assert StubAvatarService.drives == [
        ("古建筑讲解：这是一处保存完整的传统建筑。资料来源：古建筑（景区档案）。", "curious", "explain")
    ]


def test_perception_websocket_appends_source_and_preserves_it_when_truncated(client, monkeypatch):
    import app.api.v1.perception as perception_api

    stub_perception = StubPerceptionService(_target_result())
    StubRetrievalService.hits = [_stub_hit()]
    StubGenerationService.calls = []
    monkeypatch.setattr(StubGenerationService, "text", "古建筑讲解内容。" + "讲解细节。" * 80)
    monkeypatch.setattr(perception_api, "PerceptionService", lambda: stub_perception)
    monkeypatch.setattr(perception_api, "RetrievalService", StubRetrievalService)
    monkeypatch.setattr(perception_api, "GenerationService", StubGenerationService, raising=False)
    monkeypatch.setattr(perception_api, "AvatarService", StubAvatarService)

    with client.websocket_connect("/api/v1/ws/perception") as ws:
        assert ws.receive_json()["type"] == "ready"
        for _ in range(3):
            ws.send_bytes(sample_frame(320, 240))
            message = ws.receive_json()

    interaction = message["interaction"]
    assert len(interaction["text"]) <= 200
    assert interaction["text"].endswith("资料来源：古建筑（景区档案）。")
    assert interaction["text"].count("资料来源：") == 1


def test_perception_websocket_long_sources_stay_within_text_limit(client, monkeypatch):
    import app.api.v1.perception as perception_api

    stub_perception = StubPerceptionService(_target_result())
    StubRetrievalService.hits = [
        Hit(
            chunk=KbChunkData(
                id=f"kb-{index}",
                title=f"{name}古建筑" + "超长标题" * 40,
                content="资料内容",
                source=f"{name}档案馆" + "超长来源" * 40,
            ),
            score=0.95 - index * 0.01,
        )
        for index, name in enumerate(("一号", "二号", "三号"), start=1)
    ]
    monkeypatch.setattr(StubGenerationService, "text", "讲解正文。" * 80)
    monkeypatch.setattr(perception_api, "PerceptionService", lambda: stub_perception)
    monkeypatch.setattr(perception_api, "RetrievalService", StubRetrievalService)
    monkeypatch.setattr(perception_api, "GenerationService", StubGenerationService)
    monkeypatch.setattr(perception_api, "AvatarService", StubAvatarService)

    with client.websocket_connect("/api/v1/ws/perception") as ws:
        assert ws.receive_json()["type"] == "ready"
        for _ in range(3):
            ws.send_bytes(sample_frame(320, 240))
            message = ws.receive_json()

    text = message["interaction"]["text"]
    assert len(text) <= 200
    assert "资料来源：" in text
    assert "一号古建筑" in text
    assert "一号档案馆" in text


def test_perception_websocket_no_hit_uses_fixed_clarification_text(client, monkeypatch):
    import app.api.v1.perception as perception_api

    stub_perception = StubPerceptionService(_target_result())
    StubRetrievalService.calls = []
    StubRetrievalService.hits = []
    StubGenerationService.calls = []
    StubAvatarService.drives = []
    monkeypatch.setattr(perception_api, "PerceptionService", lambda: stub_perception)
    monkeypatch.setattr(perception_api, "RetrievalService", StubRetrievalService)
    monkeypatch.setattr(perception_api, "GenerationService", StubGenerationService, raising=False)
    monkeypatch.setattr(perception_api, "AvatarService", StubAvatarService)

    with client.websocket_connect("/api/v1/ws/perception") as ws:
        assert ws.receive_json()["type"] == "ready"
        messages = []
        for _ in range(3):
            ws.send_bytes(sample_frame(320, 240))
            messages.append(ws.receive_json())
        message = messages[-1]

    interaction = message["interaction"]
    assert interaction["kind"] == "clarification"
    assert "重新拍摄" in interaction["text"]
    assert interaction["drive"]["emotion"] == "gentle"
    assert interaction["drive"]["motion"] == "nod"
    assert StubGenerationService.calls == []
    assert StubAvatarService.drives == [(interaction["text"], "gentle", "nod")]


def test_perception_websocket_retrieval_failure_uses_clarification_without_generation(client, monkeypatch):
    import app.api.v1.perception as perception_api

    class FailingRetrievalService:
        def text_to_text(self, *args, **kwargs):
            raise RuntimeError("retrieval unavailable")

    stub_perception = StubPerceptionService(_target_result())
    StubGenerationService.calls = []
    monkeypatch.setattr(perception_api, "PerceptionService", lambda: stub_perception)
    monkeypatch.setattr(perception_api, "RetrievalService", FailingRetrievalService)
    monkeypatch.setattr(perception_api, "GenerationService", StubGenerationService, raising=False)
    monkeypatch.setattr(perception_api, "AvatarService", StubAvatarService)

    with client.websocket_connect("/api/v1/ws/perception") as ws:
        assert ws.receive_json()["type"] == "ready"
        for _ in range(3):
            ws.send_bytes(sample_frame(320, 240))
            message = ws.receive_json()

    assert message["interaction"]["kind"] == "clarification"
    assert "资料来源：" not in message["interaction"]["text"]
    assert StubGenerationService.calls == []


def test_perception_websocket_generation_failure_uses_clarification(client, monkeypatch):
    import app.api.v1.perception as perception_api

    class FailingGenerationService:
        def generate(self, *args, **kwargs):
            raise RuntimeError("generation unavailable")

    stub_perception = StubPerceptionService(_target_result())
    StubRetrievalService.hits = [_stub_hit()]
    monkeypatch.setattr(perception_api, "PerceptionService", lambda: stub_perception)
    monkeypatch.setattr(perception_api, "RetrievalService", StubRetrievalService)
    monkeypatch.setattr(perception_api, "GenerationService", FailingGenerationService, raising=False)
    monkeypatch.setattr(perception_api, "AvatarService", StubAvatarService)

    with client.websocket_connect("/api/v1/ws/perception") as ws:
        assert ws.receive_json()["type"] == "ready"
        for _ in range(3):
            ws.send_bytes(sample_frame(320, 240))
            message = ws.receive_json()

    assert message["interaction"]["kind"] == "clarification"
    assert "资料来源：" not in message["interaction"]["text"]


def test_perception_websocket_empty_generation_uses_clarification(client, monkeypatch):
    import app.api.v1.perception as perception_api

    class EmptyGenerationService:
        def generate(self, *args, **kwargs):
            return None

    stub_perception = StubPerceptionService(_target_result())
    StubRetrievalService.hits = [_stub_hit()]
    monkeypatch.setattr(perception_api, "PerceptionService", lambda: stub_perception)
    monkeypatch.setattr(perception_api, "RetrievalService", StubRetrievalService)
    monkeypatch.setattr(perception_api, "GenerationService", EmptyGenerationService, raising=False)
    monkeypatch.setattr(perception_api, "AvatarService", StubAvatarService)

    with client.websocket_connect("/api/v1/ws/perception") as ws:
        assert ws.receive_json()["type"] == "ready"
        for _ in range(3):
            ws.send_bytes(sample_frame(320, 240))
            message = ws.receive_json()

    assert message["interaction"]["kind"] == "clarification"
    assert message["interaction"]["text"] != "None资料来源：古建筑（景区档案）。"


def test_perception_websocket_greeting_keeps_legacy_avatar(client, monkeypatch):
    import app.api.v1.perception as perception_api

    stub_perception = StubPerceptionService(_wave_result())
    StubAvatarService.drives = []
    StubAvatarService.greetings = []
    monkeypatch.setattr(perception_api, "PerceptionService", lambda: stub_perception)
    monkeypatch.setattr(perception_api, "AvatarService", StubAvatarService)

    with client.websocket_connect("/api/v1/ws/perception") as ws:
        assert ws.receive_json()["type"] == "ready"
        ws.send_bytes(sample_frame(320, 240))
        message = ws.receive_json()

    assert message["suggestion"]["action"] == "greet"
    assert set(message["avatar"]) == {"text", "gesture", "drive"}
    assert message["avatar"]["text"] == "你好"
    assert message["avatar"]["gesture"] == "挥手"
    assert message["avatar"]["drive"]["motion"] == "wave"
    assert message["interaction"]["kind"] == "greeting"
    assert message["interaction"]["gesture"] == "挥手"
    assert message["interaction"]["drive"]["motion"] == "wave"


def test_perception_websocket_state_is_connection_scoped(client, monkeypatch):
    import app.api.v1.perception as perception_api

    stub_perception = StubPerceptionService(_target_result())
    monkeypatch.setattr(perception_api, "PerceptionService", lambda: stub_perception)
    monkeypatch.setattr(perception_api, "AvatarService", StubAvatarService)

    with client.websocket_connect("/api/v1/ws/perception") as first:
        assert first.receive_json()["type"] == "ready"
        for _ in range(2):
            first.send_bytes(sample_frame(320, 240))
            assert first.receive_json()["interaction"] is None

    with client.websocket_connect("/api/v1/ws/perception") as second:
        assert second.receive_json()["type"] == "ready"
        second.send_bytes(sample_frame(320, 240))
        assert second.receive_json()["interaction"] is None


def test_perception_websocket_drive_failure_returns_clarification(client, monkeypatch):
    import app.api.v1.perception as perception_api

    def failing_drive(self, *args, **kwargs):
        raise RuntimeError("avatar drive unavailable")

    stub_perception = StubPerceptionService(_target_result())
    StubRetrievalService.hits = [_stub_hit()]
    monkeypatch.setattr(perception_api, "PerceptionService", lambda: stub_perception)
    monkeypatch.setattr(perception_api, "RetrievalService", StubRetrievalService)
    monkeypatch.setattr(perception_api, "GenerationService", StubGenerationService, raising=False)
    monkeypatch.setattr(StubAvatarService, "drive", failing_drive)
    monkeypatch.setattr(perception_api, "AvatarService", StubAvatarService)

    with client.websocket_connect("/api/v1/ws/perception") as ws:
        assert ws.receive_json()["type"] == "ready"
        for _ in range(3):
            ws.send_bytes(sample_frame(320, 240))
            message = ws.receive_json()
        ws.send_text('{"ping": true}')
        assert ws.receive_json()["type"] == "pong"

    assert message["type"] == "perception"
    assert message["interaction"]["kind"] == "clarification"
    assert "重新拍摄" in message["interaction"]["text"]
    assert message["interaction"]["drive"] is None
    assert message["data"]["detections"][0]["label"] == "古建筑"


def test_perception_websocket_avatar_initialization_failure_keeps_perception_available(client, monkeypatch):
    import app.api.v1.perception as perception_api

    def failing_avatar_init():
        raise RuntimeError("avatar unavailable")

    stub_perception = StubPerceptionService(_target_result())
    monkeypatch.setattr(perception_api, "PerceptionService", lambda: stub_perception)
    monkeypatch.setattr(perception_api, "AvatarService", failing_avatar_init)

    with client.websocket_connect("/api/v1/ws/perception") as ws:
        ready = ws.receive_json()
        assert ready["type"] == "ready"
        assert ready["degraded"]["component"] == "avatar"
        for _ in range(3):
            ws.send_bytes(sample_frame(320, 240))
            message = ws.receive_json()
        assert message["type"] == "perception"
        assert message["interaction"]["kind"] == "clarification"
        assert message["interaction"]["drive"] is None
        assert message["degraded"]["component"] == "avatar"
        ws.send_text('{"ping": true}')
        assert ws.receive_json()["type"] == "pong"


def test_perception_websocket_greet_failure_returns_clarification(client, monkeypatch):
    import app.api.v1.perception as perception_api

    def failing_greet(self, *args, **kwargs):
        raise RuntimeError("avatar greet unavailable")

    stub_perception = StubPerceptionService(_wave_result())
    monkeypatch.setattr(perception_api, "PerceptionService", lambda: stub_perception)
    monkeypatch.setattr(StubAvatarService, "greet", failing_greet)
    monkeypatch.setattr(perception_api, "AvatarService", StubAvatarService)

    with client.websocket_connect("/api/v1/ws/perception") as ws:
        assert ws.receive_json()["type"] == "ready"
        ws.send_bytes(sample_frame(320, 240))
        message = ws.receive_json()
        ws.send_text('{"ping": true}')
        assert ws.receive_json()["type"] == "pong"

    assert message["type"] == "perception"
    assert message["interaction"]["kind"] == "clarification"
    assert message["interaction"]["gesture"] == "挥手"
    assert message["interaction"]["drive"] is None


def test_perception_websocket_analyze_failure_returns_clarification_and_stays_open(client, monkeypatch):
    import app.api.v1.perception as perception_api

    def failing_analyze(self, *args, **kwargs):
        raise RuntimeError("perception unavailable")

    stub_perception = StubPerceptionService(_target_result())
    monkeypatch.setattr(stub_perception, "analyze", failing_analyze.__get__(stub_perception))
    monkeypatch.setattr(perception_api, "PerceptionService", lambda: stub_perception)
    monkeypatch.setattr(perception_api, "AvatarService", StubAvatarService)

    with client.websocket_connect("/api/v1/ws/perception") as ws:
        assert ws.receive_json()["type"] == "ready"
        ws.send_bytes(sample_frame(320, 240))
        message = ws.receive_json()
        assert message["type"] == "perception"
        assert message["data"] == {}
        assert message["suggestion"] is None
        assert message["interaction"]["kind"] == "clarification"
        assert message["degraded"]["component"] == "perception"
        ws.send_text('{"ping": true}')
        assert ws.receive_json()["type"] == "pong"


def test_perception_websocket_tts_failure_keeps_silent_drive(client, monkeypatch):
    import app.api.v1.perception as perception_api
    import app.services.avatar as avatar_service

    class FailingTts:
        name = "stub:tts"

        def synthesize(self, *args, **kwargs):
            raise RuntimeError("tts unavailable")

    stub_perception = StubPerceptionService(_target_result())
    StubRetrievalService.hits = [_stub_hit()]
    monkeypatch.setattr(perception_api, "PerceptionService", lambda: stub_perception)
    monkeypatch.setattr(perception_api, "RetrievalService", StubRetrievalService)
    monkeypatch.setattr(perception_api, "GenerationService", StubGenerationService, raising=False)
    monkeypatch.setattr(avatar_service, "get_tts", lambda: FailingTts())

    with client.websocket_connect("/api/v1/ws/perception") as ws:
        assert ws.receive_json()["type"] == "ready"
        messages = []
        for _ in range(3):
            ws.send_bytes(sample_frame(320, 240))
            messages.append(ws.receive_json())
        message = messages[-1]

    drive = message["interaction"]["drive"]
    assert drive["audio"] is None
    assert drive["degraded"]
    assert drive["visemes"]
    assert drive["duration_ms"] > 0


# ------------------------------ 能力回显 ------------------------------
def test_readyz_declares_cv_stack(client):
    stack = client.get("/api/v1/readyz").json()["data"]["stack"]
    assert "Milvus" in stack["vector_store"]
    assert "Qwen" in stack["llm"]
