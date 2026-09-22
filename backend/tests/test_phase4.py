"""工单19 · 阶段四接口测试（对接真实技术栈）

工单编号：人工智能CV-AIGC-19-文旅Agent任务工单-创意策划与内容生成

覆盖：线路策划 / 活动推荐 / 攻略流程图 / 旅行日记 / 短视频合成 / 图像异步任务 /
分享链路 / 产物访问。与阶段二、三的测试一致，直接对接真实技术栈（PostgreSQL+PostGIS /
Redis / Milvus / MinIO / FFmpeg），不做替代实现，运行前需先起 docker-compose 并灌库：

    python scripts/seed_kb.py && python scripts/seed_places.py

关于图像生成用例：Qwen-Image 走云端额度，因此用例只断言**异步入队**的正确性
（返回 task_id 且任务已登记），不对生成结果做强断言，避免把外部额度变成测试的硬依赖。
"""
from __future__ import annotations

import io

from PIL import Image


def sample_jpeg(color: tuple[int, int, int] = (150, 175, 155), size: tuple[int, int] = (900, 640)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


def _first_activity(client) -> dict | None:
    """取一条真实活动用于攻略用例；活动表为空时跳过相关断言。"""
    response = client.post("/api/v1/activity/recommend", json={"interests": [], "limit": 1})
    items = (response.json().get("data") or {}).get("items") or []
    return items[0] if items else None


# --------------------------------------------------------------------------
# 1. 个性化线路与活动生成
# --------------------------------------------------------------------------
def test_itinerary_plan_returns_real_stops(client):
    """行程分站必须来自真实景点数据，且带时间与理由。"""
    response = client.post(
        "/api/v1/itinerary/plan",
        json={"interests": ["历史", "美食"], "theme": "文化深度游", "duration": "半日", "pace": "适中"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["title"]
    assert data["stops"], "半日游应至少产出一个分站（来自 attraction/activity 表）"
    assert data["route_text"].strip()
    for stop in data["stops"]:
        assert stop["name"]
        assert stop["index"] >= 1
        assert stop["start_time"] or stop["kind"]


def test_itinerary_plan_respects_duration(client):
    """时长档位应影响分站数量：两日 > 半日。"""
    half = client.post("/api/v1/itinerary/plan", json={"interests": ["历史"], "duration": "半日"}).json()["data"]
    two_days = client.post("/api/v1/itinerary/plan", json={"interests": ["历史"], "duration": "两日"}).json()["data"]
    assert len(two_days["stops"]) >= len(half["stops"])


def test_itinerary_plan_without_interests_still_works(client):
    """无兴趣输入属于合法降级场景，接口必须仍然可用。"""
    response = client.post("/api/v1/itinerary/plan", json={"interests": [], "duration": "半日"})
    assert response.status_code == 200
    assert response.json()["data"]["stops"] is not None


# --------------------------------------------------------------------------
# 2. 活动与体验推荐
# --------------------------------------------------------------------------
def test_activity_recommend(client):
    response = client.post("/api/v1/activity/recommend", json={"interests": ["非遗", "美食"], "limit": 5})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["items"], "活动表已灌库，应至少推荐一项"
    assert data["advice"]
    for item in data["items"]:
        assert item["id"] and item["name"]


def test_activity_recommend_with_geo_uses_postgis(client):
    """带经纬度时应走 PostGIS 距离排序，并在半径内返回结果。"""
    response = client.post(
        "/api/v1/activity/recommend",
        json={"interests": [], "latitude": 30.2475, "longitude": 120.1466, "radius_m": 5000, "limit": 5},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["has_geo"] is True
    for item in data["items"]:
        assert item["distance_m"] is not None
        assert item["distance_m"] <= 5000


def test_activity_recommend_keyword_filter(client):
    response = client.post("/api/v1/activity/recommend", json={"keyword": "点茶", "limit": 5})
    assert response.status_code == 200


# --------------------------------------------------------------------------
# 3. 攻略与流程图
# --------------------------------------------------------------------------
def test_create_guide_with_diagram(client):
    activity = _first_activity(client)
    assert activity is not None, "活动表为空，请先执行 scripts/seed_places.py"

    response = client.post("/api/v1/create/guide", json={"activity_id": activity["id"], "interests": ["非遗"]})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["title"]
    assert len(data["steps"]) >= 3, "兜底逻辑应保证至少 3 步，流程图才有可读结构"
    assert data["mermaid"].startswith("---") and "flowchart" in data["mermaid"]
    assert data["guide_text"]
    assert data["diagram_url"]

    # 流程图必须是可下载的真实 PNG
    raw = client.get(data["diagram_url"])
    assert raw.status_code == 200
    image = Image.open(io.BytesIO(raw.content))
    assert image.format == "PNG"
    assert image.width > 400 and image.height > 200


def test_create_guide_unknown_activity(client):
    response = client.post("/api/v1/create/guide", json={"activity_id": "not-exist-id"})
    assert response.status_code == 404


# --------------------------------------------------------------------------
# 4. 旅行日记
# --------------------------------------------------------------------------
def test_create_diary(client):
    response = client.post(
        "/api/v1/create/diary",
        json={"title": "西湖一日", "tone": "温暖记录", "place": "西湖", "highlights": ["断桥晨雾", "苏堤春晓"]},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["kind"] == "diary"
    assert len(data["text_content"]) > 20
    assert data["size_bytes"] > 0
    # 标题与亮点应体现在正文里（LLM 不可用时由模板兜底，同样成立）
    assert "西湖" in data["text_content"] or "西湖" in data["title"]


# --------------------------------------------------------------------------
# 5. 短视频 / 电子相册
# --------------------------------------------------------------------------
def test_create_video_sync(client):
    """同步合成：FFmpeg + OpenCV 链路不依赖外部模型，可直接断言成片参数。"""
    files = [
        ("files", (f"p{index}.jpg", sample_jpeg(color), "image/jpeg"))
        for index, color in enumerate([(150, 175, 155), (170, 165, 140), (140, 160, 180)])
    ]
    response = client.post(
        "/api/v1/create/video",
        files=files,
        data={"title": "西湖漫步", "captions": "清晨入古寺|曲径通幽处|潭影空人心", "background": "false"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["mime"] == "video/mp4"
    assert data["size_bytes"] > 20000
    extra = data["extra"]
    assert extra["width"] == 1280 and extra["height"] == 720
    assert extra["frames"] > 0
    # 3 段 2.6s、两次 0.6s 交叉淡入 → 6.6s
    assert abs(extra["duration_seconds"] - 6.6) < 0.5

    raw = client.get(data["url"])
    assert raw.status_code == 200
    assert raw.content[:4] == b"\x00\x00\x00\x18" or b"ftyp" in raw.content[:16]  # MP4 容器标识


def test_create_video_requires_photos(client):
    response = client.post("/api/v1/create/video", data={"background": "false"})
    assert response.status_code in (400, 422)


# --------------------------------------------------------------------------
# 6. 图像生成（异步入队）
# --------------------------------------------------------------------------
def test_create_image_enqueues_task(client):
    files = [("files", ("a.jpg", sample_jpeg(), "image/jpeg"))]
    response = client.post(
        "/api/v1/create/image",
        files=files,
        data={"kind": "postcard", "style": "ink", "title": "测试明信片", "background": "true"},
    )
    assert response.status_code == 200
    task = response.json()["data"]
    assert task["task_id"]
    assert task["kind"] == "postcard"

    # 任务已登记，前端可立即轮询
    polled = client.get(f"/api/v1/create/task/{task['task_id']}")
    assert polled.status_code == 200
    assert polled.json()["data"]["status"] in {"pending", "running", "success", "failed"}


def test_create_image_rejects_unknown_kind(client):
    files = [("files", ("a.jpg", sample_jpeg(), "image/jpeg"))]
    response = client.post("/api/v1/create/image", files=files, data={"kind": "unknown"})
    assert response.status_code == 400


def test_create_image_rejects_non_image(client):
    files = [("files", ("a.txt", b"not an image", "text/plain"))]
    response = client.post("/api/v1/create/image", files=files, data={"kind": "artistic"})
    assert response.status_code == 400


def test_task_not_found(client):
    assert client.get("/api/v1/create/task/does-not-exist").status_code == 404


# --------------------------------------------------------------------------
# 7. 多模态输出与分享
# --------------------------------------------------------------------------
def test_share_flow(client):
    diary = client.post(
        "/api/v1/create/diary",
        json={"title": "分享用日记", "place": "西湖", "highlights": ["苏堤春晓"]},
    ).json()["data"]

    created = client.post(
        "/api/v1/share",
        json={"asset_id": diary["id"], "channel": "poster", "title": "分享用日记", "summary": "来自测试的分享"},
    )
    assert created.status_code == 200
    shared = created.json()["data"]
    assert shared["token"] and shared["url"].endswith(shared["token"])
    assert shared["poster_url"], "海报应合成成功（日记类走纯 Pillow 排版，不依赖外部模型）"

    # 落地页数据
    view = client.get(f"/api/v1/share/{shared['token']}")
    assert view.status_code == 200
    payload = view.json()["data"]
    assert payload["asset"]["kind"] == "diary"
    assert payload["visits"] >= 1

    # 海报是真实 JPEG
    poster = client.get(shared["poster_url"])
    assert poster.status_code == 200
    image = Image.open(io.BytesIO(poster.content))
    assert image.format == "JPEG"
    assert image.size == (1080, 1440)


def test_share_without_content(client):
    assert client.post("/api/v1/share", json={}).status_code == 400


def test_share_unknown_token(client):
    assert client.get("/api/v1/share/not-a-real-token").status_code == 404


def test_share_unknown_asset(client):
    response = client.post("/api/v1/share", json={"asset_id": "no-such-asset"})
    assert response.status_code == 404


# --------------------------------------------------------------------------
# 8. 产物访问与创作列表
# --------------------------------------------------------------------------
def test_list_assets(client):
    response = client.get("/api/v1/create/assets")
    assert response.status_code == 200
    data = response.json()["data"]
    assert "items" in data and "total" in data
    assert data["total"] >= 1


def test_asset_file_not_found(client):
    assert client.get("/api/v1/create/asset/no-such-id/file").status_code == 404


def test_asset_file_served_by_backend(client):
    """产物由后端代理转发（不依赖 MinIO 端口可达），且 mime 与内容一致。"""
    assets = client.get("/api/v1/create/assets").json()["data"]["items"]
    target = next((item for item in assets if item["url"]), None)
    assert target is not None
    raw = client.get(target["url"])
    assert raw.status_code == 200
    assert len(raw.content) == target["size_bytes"]
    assert raw.headers["content-type"].startswith(target["mime"].split(";")[0])
