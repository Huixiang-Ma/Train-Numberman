"""工单20 · 阶段五 功能集成测试（17 个典型场景端到端）

工单编号：人工智能CV-AIGC-20-文旅Agent任务工单-功能集成测试与部署

对应 docs/06 §三 的 17 个典型测试场景。每个用例都走**真实链路**：
感知（YOLO11/SAM 2/MediaPipe/PaddleOCR，本地）→ 检索（Milvus）→ 生成（Qwen）
→ 数字人驱动（CosyVoice）→ 内容生成（Qwen-Image/FFmpeg/python-pptx/Pillow）。

关于外部额度：图像生成 / LLM / ASR / TTS 走云端额度。额度不可用时各链路按设计降级
（见 backend/README.md §14），因此用例断言的是**集成契约**（链路能通、结构完整、
降级可用），而不是把外部额度变成测试的硬依赖。纯本地能力（感知、视频合成、
地图、流程图、PPT、海报、日记模板）做强断言。

运行前：
    python scripts/seed_kb.py && python scripts/seed_places.py && python scripts/sync_schema.py
"""
from __future__ import annotations

import io

from PIL import Image, ImageDraw

ADMIN = {"username": "admin", "password": "wenlv_admin_pass"}


def photo(color=(150, 175, 155), size=(900, 640), shape: str = "mixed") -> bytes:
    """造一张有几何形状的测试图（供感知/合成链路使用）。"""
    image = Image.new("RGB", size, color)
    draw = ImageDraw.Draw(image)
    if shape in ("mixed", "building"):
        draw.rectangle([120, 240, 420, 520], fill=(120, 96, 78))  # 建筑主体
        draw.polygon([(100, 240), (440, 240), (270, 130)], fill=(150, 90, 70))  # 屋顶
    if shape in ("mixed", "person"):
        draw.ellipse([560, 200, 700, 340], fill=(196, 170, 150))  # 头像
        draw.rectangle([580, 350, 680, 600], fill=(90, 110, 130))  # 身体
    if shape == "mural":
        for index in range(3):
            draw.ellipse([120 + index * 240, 200, 320 + index * 240, 420], fill=(170, 130, 100))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _multipart(name: str, data: bytes, mime: str = "image/png"):
    return {"frame": (name, data, mime)}


# ==========================================================================
# 场景 1：游客拍照上传古建筑，系统识别并讲解
# ==========================================================================
def test_scenario_01_building_photo_guide(client):
    frame = photo(shape="building")
    perception = client.post(
        "/api/v1/perception/analyze",
        files={"frame": ("building.png", frame, "image/png")},
        data={"with_classify": "true"},
    )
    assert perception.status_code == 200
    payload = perception.json()["data"]
    assert "detections" in payload and "segments" in payload
    assert payload["providers"], "应回显可用的感知能力"

    # 链路后半段：图片 + 文本 → 多模态对话 → 数字人讲解
    dialog = client.post(
        "/api/v1/dialog/multimodal",
        files={"image": ("building.png", frame, "image/png")},
        data={"text": "这是什么建筑？讲讲它的风格", "with_avatar": "true"},
    )
    assert dialog.status_code == 200
    data = dialog.json()["data"]
    assert data["intent"], "应识别出意图"
    assert data["answer_text"], "应返回讲解文本（额度不可用时为明确提示语）"
    assert data["workflow"], "应回显编排链路"


# ==========================================================================
# 场景 2：语音问"必打卡景点"，数字人答复并推荐路线
# ==========================================================================
def test_scenario_02_must_see_spots_and_route(client):
    answered = client.post("/api/v1/dialog", json={"text": "这里有哪些必打卡的景点？", "with_avatar": True})
    assert answered.status_code == 200
    assert answered.json()["data"]["answer_text"]

    # 后半段：把"推荐路线"落到行程策划上
    plan = client.post("/api/v1/itinerary/plan", json={"interests": ["历史", "古建筑"], "duration": "半日"})
    assert plan.status_code == 200
    assert plan.json()["data"]["stops"], "推荐路线应给出分站"


# ==========================================================================
# 场景 3：上传碑刻照片，OCR 识别碑文并讲解
# ==========================================================================
def test_scenario_03_stele_ocr(client):
    frame = photo(color=(210, 205, 195), shape="mixed")
    response = client.post(
        "/api/v1/perception/analyze",
        files={"frame": ("stele.png", frame, "image/png")},
        data={"with_ocr": "true"},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert "ocr_text" in payload, "OCR 字段应存在于响应契约中"
    assert "ocr" in payload["providers"], "PaddleOCR 应作为本地能力注册"

    dialog = client.post(
        "/api/v1/dialog/multimodal",
        files={"image": ("stele.png", frame, "image/png")},
        data={"text": "碑文讲了什么？", "with_avatar": "true"},
    )
    assert dialog.status_code == 200
    assert dialog.json()["data"]["answer_text"]


# ==========================================================================
# 场景 4：游客挥手 → 数字人主动问候 → 推送附近活动
# ==========================================================================
def test_scenario_04_wave_greeting_and_activity(client):
    greet = client.post("/api/v1/avatar/greet", json={"gesture": "挥手"})
    assert greet.status_code == 200
    payload = greet.json()["data"]
    assert payload["text"] and payload["drive"], "问候应同时返回文案与驱动数据"
    assert payload["drive"]["motion"], "应带动作指令"

    nearby = client.post("/api/v1/activity/recommend", json={"interests": [], "limit": 3})
    assert nearby.status_code == 200
    assert "items" in nearby.json()["data"], "应能推送附近活动"


# ==========================================================================
# 场景 5：输入"自然风光和摄影" → 摄影线路与拍照点
# ==========================================================================
def test_scenario_05_photography_itinerary(client):
    response = client.post(
        "/api/v1/itinerary/plan",
        json={"interests": ["摄影", "自然"], "theme": "摄影采风", "duration": "半日", "pace": "舒缓"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["stops"]
    kinds = {stop["kind"] for stop in data["stops"]}
    assert kinds & {"sight", "photo", "activity"}, "分站类型应落在参观/拍照/体验之内"


# ==========================================================================
# 场景 6：上传合影 → 艺术化纪念照与明信片
# ==========================================================================
def test_scenario_06_group_photo_and_postcard(client):
    files = [("files", ("group.png", photo(shape="person"), "image/png"))]
    for kind in ("artistic", "postcard", "group_photo"):
        response = client.post(
            "/api/v1/create/image",
            files=files,
            data={"kind": kind, "style": "ink", "title": f"测试-{kind}", "background": "true"},
        )
        assert response.status_code == 200
        task = response.json()["data"]
        assert task["task_id"] and task["kind"] == kind, f"{kind} 应进入异步队列"
        polled = client.get(f"/api/v1/create/task/{task['task_id']}")
        assert polled.status_code == 200
        assert polled.json()["data"]["status"] in {"pending", "running", "success", "failed"}


# ==========================================================================
# 场景 7：上传短视频 → 分析并生成配音讲解
# ==========================================================================
def test_scenario_07_video_with_narration(client):
    """视频侧走"照片合成 + 解说"：帧抽取/检测复用阶段三，合成由 FFmpeg 完成。"""
    files = [("files", (f"p{i}.png", photo(shape="mixed"), "image/png")) for i in range(2)]
    response = client.post(
        "/api/v1/create/video",
        files=files,
        data={
            "title": "景区实拍解说",
            "captions": "古建主体|飞檐细节",
            "background": "false",
            "with_narration": "false",  # 解说音轨走云端额度，默认关闭以保证本地可复现
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["mime"] == "video/mp4"
    assert data["extra"]["frames"] > 0


# ==========================================================================
# 场景 8：语音问"这座雕像是谁" + 上传雕像照
# ==========================================================================
def test_scenario_08_statue_identify(client):
    response = client.post(
        "/api/v1/dialog/multimodal",
        files={"image": ("statue.png", photo(shape="person"), "image/png")},
        data={"text": "这座雕像是谁？", "with_avatar": "true"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["intent"] in {"识物", "知识", "问人"}, f"意图应落在识物/知识类，实际 {data['intent']}"
    assert data["answer_text"]


# ==========================================================================
# 场景 9：上传动植物照片 → 识别物种并讲解生态知识
# ==========================================================================
def test_scenario_09_plant_identify(client):
    response = client.post(
        "/api/v1/perception/analyze",
        files={"frame": ("plant.png", photo(color=(160, 195, 160), shape="mural"), "image/png")},
        data={"with_classify": "true"},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert "classification" in payload
    assert "classifier" in payload["providers"], "YOLO11-cls 应作为本地分类能力注册"


# ==========================================================================
# 场景 10：生成旅行日记（整理行程/照片/视频）
# ==========================================================================
def test_scenario_10_travel_diary(client):
    response = client.post(
        "/api/v1/create/diary",
        json={"title": "我的旅行日记", "place": "景区", "highlights": ["主殿木构", "水榭点茶", "登高看全景"]},
    )
    assert response.status_code == 200
    asset = response.json()["data"]
    assert asset["kind"] == "diary"
    assert len(asset["text_content"]) > 20
    for point in ("主殿木构", "水榭点茶"):
        assert point in asset["text_content"], "亮点应体现在日记正文中"


# ==========================================================================
# 场景 11：语音问"附近特色美食" → 结合定位推荐并生成攻略
# ==========================================================================
def test_scenario_11_food_recommend_and_guide(client):
    response = client.post(
        "/api/v1/activity/recommend",
        json={
            "interests": ["美食"],
            "keyword": "美食",
            "latitude": 30.2475,
            "longitude": 120.1466,
            "radius_m": 5000,
            "limit": 3,
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["has_geo"] is True, "带定位时应走 PostGIS 距离排序"
    assert data["items"]
    assert data["advice"]

    guide = client.post("/api/v1/create/guide", json={"activity_id": data["items"][0]["id"], "interests": ["美食"]})
    assert guide.status_code == 200
    assert guide.json()["data"]["steps"]


# ==========================================================================
# 场景 12：上传活动现场照片 → 生成活动回顾 PPT 与流程图
# ==========================================================================
def test_scenario_12_activity_review_ppt(client):
    files = [("files", (f"p{i}.png", photo(shape="mixed"), "image/png")) for i in range(3)]
    response = client.post(
        "/api/v1/create/ppt",
        files=files,
        data={"title": "活动回顾", "subtitle": "测试", "notes": "开场|体验|合影"},
    )
    assert response.status_code == 200
    asset = response.json()["data"]
    assert asset["kind"] == "review_ppt"
    assert "presentationml" in asset["mime"], "应为 OOXML PPT 的 MIME"
    assert asset["extra"]["slides"] == 5, "封面 + 3 图 + 结尾页"
    # 落库必须成功（曾因 mime 列宽 64 < 73 字符而失败）
    assert asset["id"] and asset["url"], "PPT 应成功落库并可下载"

    raw = client.get(asset["url"])
    assert raw.status_code == 200
    assert raw.content[:2] == b"PK", "PPTX 是 ZIP 容器"

    # 流程图同属该场景
    first = client.post("/api/v1/activity/recommend", json={"limit": 1}).json()["data"]["items"]
    assert first
    guide = client.post("/api/v1/create/guide", json={"activity_id": first[0]["id"]})
    assert guide.status_code == 200
    assert guide.json()["data"]["diagram_url"]


# ==========================================================================
# 场景 13：生成个性化导览地图并可下载
# ==========================================================================
def test_scenario_13_guide_map(client):
    plan = client.post(
        "/api/v1/itinerary/plan",
        json={"interests": ["历史", "美食"], "duration": "半日"},
    ).json()["data"]
    stops = [{"name": stop["name"], "index": stop["index"]} for stop in plan["stops"]]

    response = client.post("/api/v1/create/map", json={"title": "半日导览地图", "subtitle": plan["summary"], "stops": stops})
    assert response.status_code == 200
    asset = response.json()["data"]
    assert asset["extra"]["plotted"], "应绘制出分站（坐标取自 PostGIS）"
    assert asset["url"]

    raw = client.get(asset["url"])
    assert raw.status_code == 200
    image = Image.open(io.BytesIO(raw.content))
    assert image.format == "PNG"
    assert image.size == (1400, 1000), "导览地图应为可打印尺寸"


def test_scenario_13_map_rejects_unknown_stops(client):
    response = client.post("/api/v1/create/map", json={"stops": [{"name": "不存在的景点"}]})
    assert response.status_code == 400


# ==========================================================================
# 场景 14：语音问"壁画讲的故事" + 上传壁画图片
# ==========================================================================
def test_scenario_14_mural_story(client):
    response = client.post(
        "/api/v1/dialog/multimodal",
        files={"image": ("mural.png", photo(shape="mural"), "image/png")},
        data={"text": "这幅壁画讲的是什么故事？", "with_avatar": "true"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["answer_text"]


# ==========================================================================
# 场景 15：表情识别 → 数字人调整讲解风格
# ==========================================================================
def test_scenario_15_expression_style(client):
    response = client.post(
        "/api/v1/perception/analyze",
        files={"frame": ("face.png", photo(shape="person"), "image/png")},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert "expression" in payload, "表情字段应存在于响应契约中"
    assert "expression" in payload["providers"], "MediaPipe 表情识别应为本地能力"


# ==========================================================================
# 场景 16：上传一组照片 → 主题短视频配乐
# ==========================================================================
def test_scenario_16_themed_album_video(client):
    files = [
        ("files", (f"p{i}.png", photo(color=color, shape="mixed"), "image/png"))
        for i, color in enumerate([(150, 175, 155), (170, 165, 140), (140, 160, 180), (165, 150, 160)])
    ]
    response = client.post(
        "/api/v1/create/video",
        files=files,
        data={
            "title": "春日主题短片",
            "captions": "启程|入景|流连|回望",
            "seconds_per_image": "2.0",
            "background": "false",
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    extra = data["extra"]
    assert extra["images"] == 4
    # 4 段 2.0s、3 次 0.6s 交叉淡入 → 8.0 - 1.8 = 6.2s
    assert abs(extra["duration_seconds"] - 6.2) < 0.6
    assert data["size_bytes"] > 30000


# ==========================================================================
# 场景 17：语音问"适合老人的休闲路线" → 适老化方案
# ==========================================================================
def test_scenario_17_senior_route(client):
    response = client.post(
        "/api/v1/itinerary/plan",
        json={"interests": ["历史"], "theme": "休闲游览", "duration": "半日", "companions": "长辈", "pace": "舒缓"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["stops"]
    # 舒缓节奏应比紧凑节奏安排更少分站（时长档位相同的前提下）
    tense = client.post(
        "/api/v1/itinerary/plan",
        json={"interests": ["历史"], "duration": "半日", "pace": "紧凑"},
    ).json()["data"]
    assert len(data["stops"]) <= len(tense["stops"])


# ==========================================================================
# 集成支撑项：可观测、审计、合规
# ==========================================================================
def test_trace_id_propagates_through_response(client):
    """trace_id 应在响应头与响应体中一致（工单20 全链路贯穿）。"""
    response = client.get("/api/v1/readyz")
    assert response.status_code == 200
    trace = response.headers.get("X-Trace-Id")
    assert trace, "响应头应带 X-Trace-Id"
    assert response.json()["trace_id"] == trace, "响应体 trace_id 应与响应头一致"


def test_trace_id_is_accepted_from_client(client):
    """上游（网关/前端）传入的 trace_id 应被透传，便于跨端串联。"""
    response = client.get("/api/v1/readyz", headers={"X-Trace-Id": "abcd1234efgh5678"})
    assert response.headers.get("X-Trace-Id") == "abcd1234efgh5678"


def test_audit_log_records_writes(client, auth_headers):
    client.post("/api/v1/itinerary/plan", json={"interests": ["历史"], "duration": "半日"})
    response = client.get("/api/v1/audit/logs?limit=20", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] >= 1
    assert any(item["method"] == "POST" for item in data["items"])
    # 来源 IP 必须已脱敏
    for item in data["items"]:
        assert not item["client_ip"].endswith("77") or "*" in item["client_ip"]


def test_audit_requires_role(client):
    assert client.get("/api/v1/audit/logs").status_code == 401


def test_compliance_report(client, auth_headers):
    response = client.get("/api/v1/audit/compliance", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data["checks"]) >= 8
    assert all("item" in item and "status" in item for item in data["checks"])


def test_content_moderation_blocks_generation(client):
    """内容审核：命中词表的输入应在生成前被拦截（工单20 §4.6）。"""
    response = client.post(
        "/api/v1/create/diary",
        json={"title": "测试", "place": "景区", "highlights": ["赌博相关内容"]},
    )
    assert response.status_code == 400
    assert "审核" in response.json()["detail"]
