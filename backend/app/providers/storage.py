"""工单17 · 对象存储（主选 MinIO）

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成
技术栈：MinIO（docs/01），保存图片 / 视频 / 音频 / 模型产物。
"""
from __future__ import annotations

import io

from .base import ObjectStorage


class MinIOStorage(ObjectStorage):
    name = "minio"

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool = False,
    ) -> None:
        from minio import Minio

        self.bucket = bucket
        self._client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
        if not self._client.bucket_exists(bucket):
            self._client.make_bucket(bucket)

    def put_object(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        self._client.put_object(
            self.bucket,
            key,
            io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        return f"minio://{self.bucket}/{key}"

    def get_object(self, key: str) -> bytes:
        response = None
        try:
            response = self._client.get_object(self.bucket, key)
            return response.read()
        finally:
            if response is not None:
                response.close()
                response.release_conn()

    def presigned_url(self, key: str, expires_seconds: int = 3600) -> str:
        from datetime import timedelta

        return self._client.presigned_get_object(self.bucket, key, expires=timedelta(seconds=expires_seconds))
