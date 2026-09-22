"""工单19 · 创意策划与内容生成的公共服务

工单编号：人工智能CV-AIGC-19-文旅Agent任务工单-创意策划与内容生成
被 itinerary / activity / creation / share 四个服务共用：内容安全校验、
LLM 结构化输出解析、对象存储写入与地址转换。
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

from ..core.config import get_settings
from ..providers.registry import get_storage

logger = logging.getLogger("wenlv.creative")

# 生成产物在对象存储中的顶层前缀（config.creation_prefix）
KIND_MIME = {
    "image": "image/png",
    "video": "video/mp4",
    "text": "text/plain; charset=utf-8",
}


# --------------------------------------------------------------------------
# 内容安全（docs/01 §七 内容审核；docs/05 §九 合规要求）
# --------------------------------------------------------------------------
class ContentRejected(RuntimeError):
    """生成内容命中安全词表，整条链路中止。"""


def check_text(*texts: str) -> None:
    """对生成内容的输入与输出做词表校验，命中即抛错。

    校验覆盖两侧：游客输入的提示词、以及模型输出的文案，
    避免"提示词合规但输出跑偏"或反之的漏检。
    """
    blocklist = get_settings().blocklist
    if not blocklist:
        return
    for text in texts:
        if not text:
            continue
        for banned in blocklist:
            if banned and banned in text:
                logger.warning("创意内容命中安全词表：%s", banned)
                raise ContentRejected("内容未通过安全审核，已拦截。请调整后重试。")


# --------------------------------------------------------------------------
# LLM 结构化输出解析
# --------------------------------------------------------------------------
def extract_json(text: str) -> Any:
    """从 LLM 输出中稳健地取出 JSON。

    模型输出常带 ```json 代码块、前后解释或收尾寒暄，单一 json.loads 极易失败。
    这里按「代码块 → 最外层花括号 → 最外层方括号」三级回退，逐级尝试。
    """
    if not text:
        return None
    candidates: list[str] = []
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fenced:
        candidates.append(fenced.group(1).strip())
    brace_start, brace_end = text.find("{"), text.rfind("}")
    if brace_start >= 0 and brace_end > brace_start:
        candidates.append(text[brace_start : brace_end + 1])
    bracket_start, bracket_end = text.find("["), text.rfind("]")
    if bracket_start >= 0 and bracket_end > bracket_start:
        candidates.append(text[bracket_start : bracket_end + 1])
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def as_list(value: Any) -> list:
    """把 LLM 可能返回的 str / dict / None 统一成列表，避免下游遍历报错。"""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (str, dict)):
        return [value]
    return []


# --------------------------------------------------------------------------
# 对象存储
# --------------------------------------------------------------------------
def store_bytes(data: bytes, kind: str, ext: str, content_type: str = "") -> str:
    """把生成产物写入对象存储，返回 minio:// URI。"""
    settings = get_settings()
    key = f"{settings.creation_prefix}/{kind}/{uuid.uuid4().hex}.{ext}"
    mime = content_type or KIND_MIME.get(kind, "application/octet-stream")
    return get_storage().put_object(key, data, content_type=mime)


def key_of(uri: str) -> str:
    """从 minio:// URI 还原对象键（与 tasks/ingest.py 的既有写法一致）。"""
    return uri.split("/", 3)[-1] if uri.startswith("minio://") else uri


def read_uri(uri: str) -> bytes:
    """读取 minio:// URI 对应的字节。"""
    return get_storage().get_object(key_of(uri))


def asset_file_url(asset_id: str) -> str:
    """生成产物的对前端可访问地址。

    不直接用 MinIO 预签名链接：预签名地址会过期、且要求浏览器能直连 MinIO
    （跨源与端口暴露问题）。改由后端代理转发，前端只需走既有 /api 代理即可。
    """
    settings = get_settings()
    return f"{settings.api_prefix}/create/asset/{asset_id}/file"


# --------------------------------------------------------------------------
# 热路径缓存（工单20 性能优化）
# --------------------------------------------------------------------------
def cache_get(key: str) -> str | None:
    """读缓存；Redis 不可用时返回 None（缓存是优化项，不应成为可用性依赖）。"""
    try:
        import redis

        value = redis.Redis.from_url(get_settings().redis_url).get(key)
        return value.decode("utf-8") if value else None
    except Exception as exc:
        logger.debug("缓存读取跳过：%s", exc)
        return None


def cache_set(key: str, value: str, ttl_seconds: int = 600) -> None:
    """写缓存；失败只记日志，绝不影响主流程。"""
    try:
        import redis

        redis.Redis.from_url(get_settings().redis_url).setex(key, ttl_seconds, value)
    except Exception as exc:
        logger.debug("缓存写入跳过：%s", exc)


def digest_key(prefix: str, *parts: Any) -> str:
    """按内容生成稳定的缓存键（顺序无关、忽略大小写）。"""
    import hashlib

    raw = "|".join(sorted(str(part).strip().lower() for part in parts if part is not None))
    return f"{prefix}:{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:20]}"
