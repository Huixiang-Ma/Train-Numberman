"""工单18 · 会话管理服务（Redis 主选）

工单编号：人工智能CV-AIGC-18-文旅Agent任务工单-智能导览与互动体验
依据 docs/04 §4.2：记录游客交互历史，实现上下文理解。
主选 Redis（多实例共享、支持 TTL）；memory 仅用于无 Redis 的单实例场景。
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Protocol

from ..core.config import get_settings


@dataclass
class Turn:
    role: str  # user | assistant
    content: str
    ts: float = field(default_factory=time.time)
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Session:
    id: str
    lang: str = "zh"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    turns: list[Turn] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


class SessionStore(Protocol):
    name: str

    def create(self, lang: str) -> Session: ...
    def get(self, session_id: str) -> Session | None: ...
    def save(self, session: Session) -> None: ...
    def drop(self, session_id: str) -> bool: ...


class RedisSessionStore:
    """主选：Redis 持久化会话。"""

    name = "redis"

    def __init__(self, url: str, ttl: int = 3600) -> None:
        import redis

        self._client = redis.Redis.from_url(url, decode_responses=True)
        self._ttl = ttl

    @staticmethod
    def _key(session_id: str) -> str:
        return f"wenlv:session:{session_id}"

    def create(self, lang: str) -> Session:
        session = Session(id=uuid.uuid4().hex[:16], lang=lang)
        self.save(session)
        return session

    def get(self, session_id: str) -> Session | None:
        raw = self._client.get(self._key(session_id))
        if not raw:
            return None
        payload = json.loads(raw)
        return Session(
            id=payload["id"],
            lang=payload.get("lang", "zh"),
            created_at=payload.get("created_at", time.time()),
            updated_at=payload.get("updated_at", time.time()),
            turns=[Turn(**item) for item in payload.get("turns", [])],
            meta=payload.get("meta") or {},
        )

    def save(self, session: Session) -> None:
        session.updated_at = time.time()
        payload = {
            "id": session.id,
            "lang": session.lang,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "turns": [turn.__dict__ for turn in session.turns],
            "meta": session.meta,
        }
        self._client.set(self._key(session.id), json.dumps(payload, ensure_ascii=False), ex=self._ttl)

    def drop(self, session_id: str) -> bool:
        return bool(self._client.delete(self._key(session_id)))


class MemorySessionStore:
    """单实例内存会话（不依赖 Redis 时使用）。"""

    name = "memory"

    def __init__(self, ttl: int = 3600) -> None:
        self._data: dict[str, Session] = {}
        self._ttl = ttl

    def create(self, lang: str) -> Session:
        session = Session(id=uuid.uuid4().hex[:16], lang=lang)
        self._data[session.id] = session
        return session

    def get(self, session_id: str) -> Session | None:
        session = self._data.get(session_id)
        if session is None:
            return None
        if time.time() - session.updated_at > self._ttl:
            self._data.pop(session_id, None)
            return None
        return session

    def save(self, session: Session) -> None:
        session.updated_at = time.time()
        self._data[session.id] = session

    def drop(self, session_id: str) -> bool:
        return self._data.pop(session_id, None) is not None


@lru_cache
def get_session_store() -> SessionStore:
    settings = get_settings()
    if settings.session_provider == "memory":
        return MemorySessionStore(settings.session_ttl_seconds)
    return RedisSessionStore(settings.redis_url, settings.session_ttl_seconds)


class SessionService:
    """会话门面：创建、读取、追加轮次、结束。"""

    def __init__(self) -> None:
        self.store: SessionStore = get_session_store()
        self.max_turns = get_settings().session_max_turns

    @property
    def provider(self) -> str:
        return self.store.name

    def create(self, lang: str = "zh") -> Session:
        return self.store.create(lang)

    def get(self, session_id: str) -> Session | None:
        return self.store.get(session_id)

    def get_or_create(self, session_id: str | None, lang: str = "zh") -> Session:
        if session_id:
            existing = self.store.get(session_id)
            if existing is not None:
                return existing
        return self.store.create(lang)

    def append(self, session: Session, role: str, content: str, **meta: Any) -> Session:
        session.turns.append(Turn(role=role, content=content, meta=meta))
        limit = self.max_turns * 2
        if len(session.turns) > limit:
            session.turns = session.turns[-limit:]
        self.store.save(session)
        return session

    def history(self, session: Session, limit: int = 6) -> list[dict[str, Any]]:
        return [
            {"role": turn.role, "content": turn.content, "ts": turn.ts, "meta": turn.meta}
            for turn in session.turns[-limit:]
        ]

    def drop(self, session_id: str) -> bool:
        return self.store.drop(session_id)
