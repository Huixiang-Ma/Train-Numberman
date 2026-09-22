"""工单17 · 文旅知识库服务

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成
职责：知识入库（PostgreSQL 元数据 + Milvus 向量）、查询、更新、删除、列表。
文本条目由 BGE-M3 向量化后写入 Milvus；图像/视频条目由 Chinese-CLIP 向量化后写入 Milvus。
"""
from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import func, select

from ..db.base import SessionLocal
from ..db.models import KbChunk, KbDocument
from ..providers.base import KbChunkData
from ..providers.registry import get_clip, get_clip_text_store, get_embedding, get_image_store, get_text_store

TEXT_MODALITIES = {"text", "structured"}
MEDIA_MODALITIES = {"image", "video"}


class KBService:
    def __init__(self) -> None:
        self.embedding = get_embedding()
        self.clip = get_clip()
        self.text_store = get_text_store()
        self.clip_text_store = get_clip_text_store()
        self.image_store = get_image_store()

    # ---------------- 入库 ----------------
    @staticmethod
    def _payloads(chunks: Sequence[KbChunkData]) -> list[str]:
        return [f"{c.title}；{' '.join(c.tags)}；{c.content}" for c in chunks]

    def ingest(self, chunks: Sequence[KbChunkData], document_title: str = "", source: str = "") -> dict:
        if not chunks:
            return {"ingested": 0, "text": 0, "clip_text": 0, "media": 0}

        text_chunks = [c for c in chunks if c.modality in TEXT_MODALITIES]
        media_chunks = [c for c in chunks if c.modality in MEDIA_MODALITIES]

        text_count = 0
        clip_text_count = 0
        if text_chunks:
            payloads = self._payloads(text_chunks)
            # BGE-M3 文本空间（语义检索） + Chinese-CLIP 文本空间（跨模态以图搜文）
            text_count = self.text_store.upsert(text_chunks, self.embedding.embed_texts(payloads))
            clip_text_count = self.clip_text_store.upsert(text_chunks, self.clip.embed_texts(payloads))

        media_count = 0
        if media_chunks:
            payloads = self._payloads(media_chunks)
            media_count = self.image_store.upsert(media_chunks, self.clip.embed_texts(payloads))

        self._persist(chunks, document_title=document_title, source=source)
        return {"ingested": len(chunks), "text": text_count, "clip_text": clip_text_count, "media": media_count}

    def _persist(self, chunks: Sequence[KbChunkData], document_title: str, source: str) -> None:
        """幂等落库：同一文档标题复用同一条 KbDocument，分块按主键 merge。"""
        title = document_title or (chunks[0].title if chunks else "未命名文档")
        with SessionLocal() as db:
            document = db.scalar(select(KbDocument).where(KbDocument.title == title))
            if document is None:
                document = KbDocument(
                    id=uuid.uuid4().hex,
                    title=title,
                    source=source or (chunks[0].source if chunks else ""),
                    authority=chunks[0].authority if chunks else "",
                    tags=[],
                )
                db.add(document)
                db.flush()
            for chunk in chunks:
                db.merge(
                    KbChunk(
                        id=chunk.id,
                        document_id=document.id,
                        title=chunk.title,
                        content=chunk.content,
                        modality=chunk.modality,
                        media_uri=chunk.media_uri,
                        tags=list(chunk.tags),
                        source=chunk.source or source,
                        vector_id=chunk.id,
                    )
                )
            db.commit()

    # ---------------- 查询 / 维护 ----------------
    def get(self, chunk_id: str) -> dict | None:
        with SessionLocal() as db:
            row = db.get(KbChunk, chunk_id)
            return self._to_dict(row) if row else None

    def list(self, limit: int = 20, offset: int = 0) -> tuple[list[dict], int]:
        with SessionLocal() as db:
            total = db.scalar(select(func.count()).select_from(KbChunk)) or 0
            rows = db.scalars(select(KbChunk).order_by(KbChunk.created_at.desc()).limit(limit).offset(offset)).all()
            return [self._to_dict(r) for r in rows], int(total)

    def update(self, chunk_id: str, patch: dict) -> dict | None:
        with SessionLocal() as db:
            row = db.get(KbChunk, chunk_id)
            if row is None:
                return None
            for field in ("title", "content", "modality", "media_uri", "source"):
                if patch.get(field) is not None:
                    setattr(row, field, patch[field])
            if patch.get("tags") is not None:
                row.tags = list(patch["tags"])
            db.commit()
            db.refresh(row)
            data = self._to_dict(row)

        chunk = KbChunkData(
            id=data["id"],
            title=data["title"],
            content=data["content"],
            modality=data["modality"],
            media_uri=data["media_uri"],
            tags=data["tags"],
            source=data["source"],
        )
        payload = [f"{chunk.title}；{chunk.content}"]
        if chunk.modality in TEXT_MODALITIES:
            self.text_store.upsert([chunk], self.embedding.embed_texts(payload))
            self.clip_text_store.upsert([chunk], self.clip.embed_texts(payload))
        else:
            self.image_store.upsert([chunk], self.clip.embed_texts(payload))
        return data

    def delete(self, chunk_id: str) -> bool:
        with SessionLocal() as db:
            row = db.get(KbChunk, chunk_id)
            if row is None:
                return False
            modality = row.modality
            db.delete(row)
            db.commit()
        if modality in TEXT_MODALITIES:
            self.text_store.delete([chunk_id])
            self.clip_text_store.delete([chunk_id])
        else:
            self.image_store.delete([chunk_id])
        return True

    def count(self) -> int:
        with SessionLocal() as db:
            return int(db.scalar(select(func.count()).select_from(KbChunk)) or 0)

    @staticmethod
    def _to_dict(row: KbChunk) -> dict:
        return {
            "id": row.id,
            "title": row.title,
            "content": row.content,
            "modality": row.modality,
            "media_uri": row.media_uri,
            "tags": list(row.tags or []),
            "source": row.source,
        }
