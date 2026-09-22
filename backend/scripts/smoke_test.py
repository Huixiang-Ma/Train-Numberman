"""工单17 · 端到端自测（对接运行中的服务）

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成
用法：python scripts/smoke_test.py [--base http://127.0.0.1:8100]
"""
from __future__ import annotations

import sys

import io

import httpx

BASE = "http://127.0.0.1:8100"


def sample_jpeg() -> bytes:
    """生成一张合法 JPEG，用于图片检索链路自测。"""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (320, 200), (138, 168, 146)).save(buffer, format="JPEG")
    return buffer.getvalue()


def main() -> None:
    global BASE
    if "--base" in sys.argv:
        BASE = sys.argv[sys.argv.index("--base") + 1]

    client = httpx.Client(base_url=BASE, timeout=900.0)

    ready = client.get("/api/v1/readyz").json()
    print("[readyz] services =", {k: v.get("ok") for k, v in ready["data"]["services"].items()})
    print("[readyz] stack    =", ready["data"]["stack"])

    token = client.post("/api/v1/auth/token", data={"username": "admin", "password": "wenlv_admin_pass"}).json()
    jwt = token["data"]["access_token"]
    headers = {"Authorization": f"Bearer {jwt}"}
    print("[auth] role =", token["data"]["role"])

    query = client.post("/api/v1/query", json={"query": "主殿的木构有什么特点", "rerank_top_n": 3}).json()["data"]
    print("[query] answer =", query["answer_text"][:90].replace("\n", " "))
    print("[query] citations =", [c["title"] for c in query["citations"]])

    search = client.post("/api/v1/search/text-to-image", json={"query": "壁画"}).json()["data"]
    print("[text-to-image] hits =", [h["title"] for h in search["hits"]])

    files = {"image": ("sample.jpg", sample_jpeg(), "image/jpeg")}
    vision = client.post("/api/v1/search/image-to-text", files=files).json()["data"]
    print("[image-to-text] hits =", [h["title"] for h in vision["hits"]], "ocr_len =", len(vision.get("ocr_text") or ""))

    ingest = client.post(
        "/api/v1/kb/ingest",
        headers=headers,
        json={
            "document_title": "自测文档",
            "source": "smoke_test",
            "chunks": [
                {
                    "id": "smoke-001",
                    "title": "自测条目",
                    "content": "这是一条用于端到端自测的文旅知识条目，用于验证入库与检索链路。",
                    "modality": "text",
                    "tags": ["自测"],
                    "source": "smoke_test",
                }
            ],
        },
    ).json()["data"]
    print("[kb/ingest] =", ingest)

    client.delete("/api/v1/kb/smoke-001", headers=headers)
    print("SMOKE_OK")


if __name__ == "__main__":
    main()
