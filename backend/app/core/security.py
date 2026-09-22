"""工单17 · 安全与鉴权（OAuth2 + JWT + RBAC）

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成
技术栈：OAuth2 密码模式 + JWT（HS256）+ RBAC 角色分级（游客/运营/管理员/专家）。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from .config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)

# RBAC 角色
ROLE_GUEST = "guest"        # 游客：检索与问答
ROLE_EDITOR = "editor"      # 运营：知识库写入
ROLE_EXPERT = "expert"      # 专家：内容审核
ROLE_ADMIN = "admin"        # 管理员：全部权限

ROLE_ORDER = {ROLE_GUEST: 0, ROLE_EDITOR: 1, ROLE_EXPERT: 2, ROLE_ADMIN: 3}


class TokenPayload(BaseModel):
    sub: str
    role: str = ROLE_GUEST
    exp: int | None = None


def hash_password(raw: str) -> str:
    return pwd_context.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    return pwd_context.verify(raw, hashed)


def create_access_token(subject: str, role: str = ROLE_GUEST, expires_minutes: int | None = None) -> str:
    settings = get_settings()
    minutes = expires_minutes or settings.access_token_expire_minutes
    expire = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    payload: dict[str, Any] = {"sub": subject, "role": role, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> TokenPayload:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="凭证无效或已过期") from exc
    return TokenPayload(**payload)


def authenticate(username: str, password: str) -> str | None:
    """内置管理员账号（生产环境应改为数据库用户表）。"""
    settings = get_settings()
    if username == settings.admin_username and password == settings.admin_password:
        return ROLE_ADMIN
    return None


async def current_token(token: str | None = Depends(oauth2_scheme)) -> TokenPayload | None:
    if not token:
        return None
    return decode_token(token)


def require_role(min_role: str):
    """RBAC 依赖：要求调用者角色不低于 min_role。"""

    async def _guard(payload: TokenPayload | None = Depends(current_token)) -> TokenPayload:
        if payload is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少访问令牌")
        if ROLE_ORDER.get(payload.role, -1) < ROLE_ORDER[min_role]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
        return payload

    return _guard
