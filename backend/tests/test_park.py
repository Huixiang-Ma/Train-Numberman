"""工单17 · 目的地 / 景区只读接口测试（docs/09 G1）

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成

注意：这是**集成测试**，依赖已灌库的 PostgreSQL（同 conftest 的其他用例）。
运行前需：启动 docker 依赖 → 启动一次应用建表 → python scripts/seed_places.py
→ python scripts/seed_parks.py

其中两个筛选用例是回归防护：它们对应的实现曾经各有一个真实缺陷——
关键词用了 func.or_（渲染成函数调用，SQL 语法错误），标签用了 json 列上的
contains()（退化成字符串 LIKE，触发 "json ~~ text"）。
"""
from __future__ import annotations


def test_destinations_listed(client):
    response = client.get("/api/v1/destination")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] >= 3
    names = [item["name"] for item in data["items"]]
    # 种子数据刻意跨三省，用来证明"通用"而不是换个名字的单景区
    assert {"杭州", "苏州", "泉州"} <= set(names)
    for item in data["items"]:
        assert isinstance(item["park_count"], int)
        assert item["park_count"] >= 1


def test_parks_listed_with_attraction_count(client):
    response = client.get("/api/v1/park")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] >= 5
    for item in data["items"]:
        assert item["destination_name"], f"{item['name']} 缺少所属目的地"
        assert item["attraction_count"] >= 1, f"{item['name']} 没有景点归属"
    assert data["has_geo"] is False  # 未传坐标时不做距离排序


def test_parks_filter_by_keyword(client):
    """回归：曾经的 func.or_ 写法会抛 SQL SyntaxError。"""
    response = client.get("/api/v1/park", params={"keyword": "园林"})
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert items, "关键词「园林」应至少命中一个景区"
    assert all("园林" in item["name"] or "园林" in item["summary"] for item in items)


def test_parks_filter_by_tag(client):
    """回归：曾经的 contains() 在 json 列上退化为 LIKE，抛 "json ~~ text"。"""
    response = client.get("/api/v1/park", params={"tag": "世界遗产"})
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert items, "至少应有 1 个景区带「世界遗产」标签"
    for item in items:
        assert "世界遗产" in item["tags"]
    # 精确匹配数组元素：带「石刻」的景区不应因为子串而混进来
    carved = client.get("/api/v1/park", params={"tag": "石刻"}).json()["data"]["items"]
    assert all("石刻" in item["tags"] for item in carved)
    assert {item["id"] for item in carved}.isdisjoint({item["id"] for item in items})


def test_parks_filter_by_destination(client):
    hz = next(
        item
        for item in client.get("/api/v1/destination").json()["data"]["items"]
        if item["name"] == "杭州"
    )
    response = client.get("/api/v1/park", params={"destination_id": hz["id"]})
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert items
    assert all(item["destination_id"] == hz["id"] for item in items)


def test_parks_sorted_by_distance(client):
    response = client.get("/api/v1/park", params={"near_lat": 31.32, "near_lon": 120.62})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["has_geo"] is True
    distances = [item["distance_m"] for item in data["items"]]
    assert all(value is not None for value in distances)
    assert distances == sorted(distances), "距离应升序"
    # 基准点取苏州，最近的应是苏州的景区
    assert data["items"][0]["destination_name"] == "苏州"


def test_park_detail_aggregates_attractions(client):
    parks = client.get("/api/v1/park").json()["data"]["items"]
    target = next(item for item in parks if item["attraction_count"] >= 2)
    response = client.get(f"/api/v1/park/{target['id']}")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == target["id"]
    assert data["destination"] is not None
    assert len(data["attractions"]) == target["attraction_count"]
    for item in data["attractions"]:
        assert item["park_id"] == target["id"]
        assert item["name"]


def test_park_detail_not_found(client):
    response = client.get("/api/v1/park/does-not-exist")
    assert response.status_code == 404
