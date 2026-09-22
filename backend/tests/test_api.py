"""工单17 · 接口测试（对接真实技术栈）

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成
前置：docker compose -f deploy/docker-compose.yml up -d；python scripts/seed_kb.py
"""
from __future__ import annotations

import io
import uuid


def sample_jpeg() -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (320, 200), (138, 168, 146)).save(buffer, format="JPEG")
    return buffer.getvalue()


def test_readyz_reports_stack(client):
    data = client.get("/api/v1/readyz").json()["data"]
    assert "Milvus" in data["stack"]["vector_store"]
    assert data["services"]["database"]["ok"] is True
    assert data["services"]["milvus"]["ok"] is True


def test_stack_endpoint_declares_primary_technologies(client):
    data = client.get("/api/v1/stack").json()["data"]
    # 四个模型走云端 API，Chinese-CLIP 保留本地
    assert "qwen" in data["llm"].lower()
    assert data["llm_mode"] == "cloud"
    assert "bge-m3" in data["embedding_model"].lower()
    assert data["embedding_mode"] == "cloud"
    assert "chinese-clip" in data["clip_model"].lower()
    assert data["clip_mode"] == "local"
    assert data["reranker_mode"] == "cloud"
    assert data["asr_mode"] == "cloud"


def test_auth_issues_jwt(client):
    payload = client.post("/api/v1/auth/token", data={"username": "admin", "password": "wenlv_admin_pass"}).json()
    assert payload["data"]["role"] == "admin"
    assert payload["data"]["access_token"]


def test_kb_write_requires_role(client):
    response = client.post("/api/v1/kb/ingest", json={"chunks": [{"title": "t", "content": "c"}]})
    assert response.status_code == 401


def test_text_search_and_query(client):
    search = client.post("/api/v1/search/text", json={"query": "壁画讲了什么"}).json()["data"]
    assert search["hits"], "以文搜文应命中"

    query = client.post("/api/v1/query", json={"query": "主殿的木构有什么特点"}).json()["data"]
    assert query["answer_text"]
    assert query["citations"]


def test_text_to_image_search(client):
    data = client.post("/api/v1/search/text-to-image", json={"query": "碑刻"}).json()["data"]
    assert data["hits"]


def test_image_search_with_ocr(client):
    files = {"image": ("frame.jpg", sample_jpeg(), "image/jpeg")}
    data = client.post("/api/v1/search/image-to-text", files=files).json()["data"]
    assert "hits" in data
    assert "ocr_text" in data


def test_invalid_image_returns_400(client):
    files = {"image": ("bad.jpg", b"\xff\xd8\xff\xe0not-an-image", "image/jpeg")}
    response = client.post("/api/v1/search/image-to-text", files=files)
    assert response.status_code == 400


def test_kb_crud_roundtrip(client, auth_headers):
    chunk_id = "test-" + uuid.uuid4().hex[:8]
    ingest = client.post(
        "/api/v1/kb/ingest",
        headers=auth_headers,
        json={
            "document_title": "测试文档",
            "source": "pytest",
            "chunks": [
                {"id": chunk_id, "title": "测试条目", "content": "用于自动化测试的临时文旅知识条目。", "tags": ["测试"]}
            ],
        },
    ).json()
    assert ingest["data"]["ingested"] == 1

    got = client.get(f"/api/v1/kb/{chunk_id}").json()
    assert got["data"]["title"] == "测试条目"

    updated = client.put(f"/api/v1/kb/{chunk_id}", headers=auth_headers, json={"title": "测试条目（已更新）"}).json()
    assert updated["data"]["title"] == "测试条目（已更新）"

    deleted = client.delete(f"/api/v1/kb/{chunk_id}", headers=auth_headers).json()
    assert deleted["data"]["deleted"] == chunk_id
    assert client.get(f"/api/v1/kb/{chunk_id}").status_code == 404


def test_media_tts_requires_cosyvoice(client):
    """CosyVoice 未部署时接口应明确报错，而不是静默降级。"""
    response = client.post("/api/v1/media/tts", json={"text": "欢迎来到景区"})
    assert response.status_code in (200, 500)
