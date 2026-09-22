"""工单17 · 向量数据库（主选 Milvus + HNSW 索引）

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成
技术栈：Milvus（docs/01），Collection 字段：id / vector / modality / tags / payload。
"""
from __future__ import annotations

from typing import Any, Sequence

from .base import Hit, KbChunkData, VectorStore


class MilvusVectorStore(VectorStore):
    name = "milvus"

    def __init__(
        self,
        uri: str,
        collection: str,
        dim: int,
        metric: str = "COSINE",
        index_type: str = "HNSW",
        hnsw_m: int = 16,
        hnsw_ef_construction: int = 200,
        search_ef: int = 64,
    ) -> None:
        from pymilvus import DataType, MilvusClient

        self.collection = collection
        self.dim = dim
        self.metric = metric
        self.search_ef = search_ef
        self._client = MilvusClient(uri=uri)

        if not self._client.has_collection(collection):
            schema = self._client.create_schema(auto_id=False, enable_dynamic_field=False)
            schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=64)
            schema.add_field("vector", DataType.FLOAT_VECTOR, dim=dim)
            schema.add_field("modality", DataType.VARCHAR, max_length=32)
            schema.add_field("tags", DataType.JSON)
            schema.add_field("payload", DataType.JSON)

            index_params = self._client.prepare_index_params()
            index_params.add_index(
                field_name="vector",
                index_type=index_type,
                metric_type=metric,
                params={"M": hnsw_m, "efConstruction": hnsw_ef_construction},
            )
            self._client.create_collection(collection_name=collection, schema=schema, index_params=index_params)

        self._client.load_collection(collection)

    # ---- 写入 ----
    def upsert(self, items: Sequence[KbChunkData], vectors: Sequence[Sequence[float]]) -> int:
        rows: list[dict[str, Any]] = []
        for item, vector in zip(items, vectors):
            rows.append(
                {
                    "id": item.id,
                    "vector": [float(x) for x in vector],
                    "modality": item.modality,
                    "tags": list(item.tags),
                    "payload": {
                        "id": item.id,
                        "title": item.title,
                        "content": item.content,
                        "modality": item.modality,
                        "media_uri": item.media_uri,
                        "tags": list(item.tags),
                        "source": item.source,
                        "authority": item.authority,
                        "meta": item.meta,
                    },
                }
            )
        if not rows:
            return 0
        self._client.upsert(collection_name=self.collection, data=rows)
        self._client.flush(self.collection)
        return len(rows)

    # ---- 检索 ----
    def search(
        self,
        vector: Sequence[float],
        top_k: int,
        modality: str | None = None,
        tags: Sequence[str] | None = None,
    ) -> list[Hit]:
        expr = f'modality == "{modality}"' if modality else ""
        results = self._client.search(
            collection_name=self.collection,
            data=[[float(x) for x in vector]],
            limit=max(top_k * 3, top_k),
            filter=expr,
            output_fields=["modality", "tags", "payload"],
            search_params={"metric_type": self.metric, "params": {"ef": self.search_ef}},
        )

        tag_filter = set(tags or [])
        hits: list[Hit] = []
        for row in results[0]:
            payload = row.get("entity", {}).get("payload") or {}
            chunk_tags = set(payload.get("tags") or [])
            if tag_filter and not tag_filter.intersection(chunk_tags):
                continue
            hits.append(
                Hit(
                    chunk=KbChunkData(
                        id=payload.get("id", row.get("id")),
                        title=payload.get("title", ""),
                        content=payload.get("content", ""),
                        modality=payload.get("modality", "text"),
                        media_uri=payload.get("media_uri"),
                        tags=list(chunk_tags),
                        source=payload.get("source", ""),
                        authority=payload.get("authority", ""),
                        meta=payload.get("meta") or {},
                    ),
                    score=float(row.get("distance", 0.0)),
                )
            )
            if len(hits) >= top_k:
                break
        return hits

    def delete(self, ids: Sequence[str]) -> int:
        if not ids:
            return 0
        self._client.delete(collection_name=self.collection, ids=list(ids))
        self._client.flush(self.collection)
        return len(ids)

    def count(self) -> int:
        try:
            stats = self._client.get_collection_stats(self.collection)
            return int(stats.get("row_count", 0))
        except Exception:
            return 0
