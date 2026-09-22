"""工单18 · 阶段三接口测试（对接真实技术栈）

工单编号：人工智能CV-AIGC-18-文旅Agent任务工单-智能导览与互动体验
覆盖：会话（Redis）/ 数字人对话（LangGraph）/ 数字人驱动（CosyVoice）/ 实时感知（YOLO11+MediaPipe）
"""
from __future__ import annotations

import io


def sample_frame(width: int = 480, height: int = 360) -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (122, 148, 132)).save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()


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


def test_perception_websocket_stream(client):
    with client.websocket_connect("/api/v1/ws/perception") as ws:
        ready = ws.receive_json()
        assert ready["type"] == "ready"
        assert ready["providers"]["gesture"].startswith("mediapipe")

        ws.send_bytes(sample_frame(320, 240))
        message = ws.receive_json()
        assert message["type"] == "perception"
        assert "detections" in message["data"]

        ws.send_text('{"ping": true}')
        assert ws.receive_json()["type"] == "pong"


# ------------------------------ 能力回显 ------------------------------
def test_readyz_declares_cv_stack(client):
    stack = client.get("/api/v1/readyz").json()["data"]["stack"]
    assert "Milvus" in stack["vector_store"]
    assert "Qwen" in stack["llm"]
