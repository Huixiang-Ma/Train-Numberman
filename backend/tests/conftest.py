"""工单17 · 测试配置

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成
说明：测试直接对接真实技术栈（PostgreSQL / Milvus / BGE-M3 / Qwen 等），
      不做任何替代实现，因此运行前需先启动 deploy/docker-compose.yml 并完成灌库。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402

ADMIN = {"username": "admin", "password": "wenlv_admin_pass"}


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def auth_headers(client) -> dict[str, str]:
    response = client.post("/api/v1/auth/token", data=ADMIN).json()
    return {"Authorization": f"Bearer {response['data']['access_token']}"}
