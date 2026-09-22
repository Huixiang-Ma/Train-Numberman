"""工单17 · 数据库会话（SQLAlchemy 2.x + PostgreSQL 16 + PostGIS）

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成
"""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from ..core.config import get_settings

settings = get_settings()

metadata = MetaData(schema=settings.db_schema)

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    metadata = metadata


def ensure_schema() -> None:
    """确保业务 schema 与 PostGIS 扩展存在（容器 initdb 已建，这里做幂等兜底）。"""
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {settings.db_schema}"))


def create_all() -> None:
    from . import models  # noqa: F401  确保模型已注册

    ensure_schema()
    Base.metadata.create_all(bind=engine)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
